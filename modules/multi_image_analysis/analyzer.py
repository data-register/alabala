# Файл: modules/multi_image_analysis/analyzer.py
"""
Логика за анализ на множество изображения от различни позиции на PTZ камерата
"""

import os
import json
import time
import threading
import httpx
from datetime import datetime
from io import BytesIO
from PIL import Image
from typing import Dict, Any, Optional, Tuple, List
import asyncio
import base64

from .config import (
    get_analysis_config, 
    update_analysis_config, 
    add_analysis_result,
    MultiAnalysisResult,
    PositionAnalysisResult
)
from modules.ptz_capture.config import get_capture_config as get_ptz_capture_config
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("multi_image_analyzer")

# Глобални променливи
analysis_thread = None

def get_anthropic_api_key() -> Optional[str]:
    """
    Взима Anthropic API ключа от средата
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY не е наличен! Моля, добавете го като секрет в средата.")
        return None
    return api_key

async def download_image(path: str) -> Optional[bytes]:
    """Чете изображение от локален файл"""
    try:
        # Проверяваме дали файлът съществува
        if not os.path.exists(path):
            logger.error(f"Файлът не съществува: {path}")
            return None
        
        # Четем файла
        with open(path, "rb") as f:
            image_data = f.read()
        
        logger.info(f"Успешно прочетено изображение от {path}, размер: {len(image_data)} bytes")
        
        # Проверяваме дали изображението е валидно
        try:
            Image.open(BytesIO(image_data))
            return image_data
        except Exception as e:
            logger.error(f"Невалидно изображение от {path}: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Грешка при четене на файл {path}: {e}")
        return None

def encode_image_base64(image_data: bytes) -> str:
    """Кодира изображението в base64"""
    return base64.b64encode(image_data).decode('utf-8')

async def analyze_image_with_anthropic(image_data: bytes, position_id: int) -> Tuple[bool, Dict[str, Any]]:
    """
    Анализира изображение с помощта на Anthropic API
    
    Args:
        image_data: Байтове на изображението
        position_id: ID на позицията
    
    Returns:
        (успех, резултат) tuple
    """
    config = get_analysis_config()
    api_key = get_anthropic_api_key()
    
    if not api_key:
        return False, {"error": "Липсва Anthropic API ключ"}
    
    try:
        # Кодираме изображението в base64
        base64_image = encode_image_base64(image_data)
        
        # Създаваме заглавки за заявката
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Определяме посоката според позицията
        direction = ""
        if position_id == 1:
            direction = "изток"
        elif position_id == 2:
            direction = "запад"
        elif position_id == 3:
            direction = "север"
        elif position_id == 4:
            direction = "юг"
        else:
            direction = f"позиция {position_id}"
        
        # Изграждаме съобщение за Claude
        prompt = f"""
        Ти си експерт метеоролог, който анализира изображения от камери. Анализирай предоставеното изображение, 
        което е направено в посока {direction.upper()} и дай детайлна информация за:
        
        1. Процент облачност (0-100%)
        2. Тип на облаците (ако има такива)
        3. Видимост (отлична, добра, умерена, лоша)
        4. Общо описание на метеорологичните условия в момента
        5. Отговори на български език
        6. Анализите между 21:00 и 06:00 българско време ги отбелязвай като: Анализа се извършва в тъмната част на деня!
        
        Отговори в следния JSON формат:
        {{
          "cloud_coverage": [число от 0 до 100],
          "cloud_type": "[тип на облаците, например: кумулус, стратус, нимбостратус и т.н.]",
          "visibility": "[отлична/добра/умерена/лоша]",
          "weather_conditions": "[кратко описание на метеорологичните условия]",
          "is_sunny": [true/false - има ли слънце на изображението],
          "confidence": [число от 0 до 100, показващо твоята увереност в анализа]
        }}
        
        Бъди възможно най-точен и прецизен. Базирай се САМО на това, което виждаш на изображението, без да правиш предположения извън видимото съдържание.
        
        Ако изображението е твърде тъмно, замъглено или по друг начин неясно, отбележи това в полето "weather_conditions" и намали стойността на "confidence".
        
        Отговори САМО с JSON обект без допълнителен текст или обяснения.
        """
        
        # Създаваме payload за заявката
        payload = {
            "model": config.anthropic_model,
            "messages": [
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image", 
                            "source": {
                                "type": "base64", 
                                "media_type": "image/jpeg", 
                                "data": base64_image
                            }
                        }
                    ]
                }
            ],
            "max_tokens": config.max_tokens,
            "temperature": config.temperature
        }
        
        logger.info(f"Изпращане на заявка към Anthropic API с модел {config.anthropic_model} за позиция {position_id}")
        start_time = time.time()
        
        # Изпращаме заявката
        async with httpx.AsyncClient() as client:
            response = await client.post(
                config.anthropic_api_url, 
                json=payload,
                headers=headers,
                timeout=60.0
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"Получен отговор от Anthropic API за позиция {position_id} за {elapsed_time:.2f} секунди")
            
            if response.status_code != 200:
                logger.error(f"Грешка от Anthropic API: {response.status_code} - {response.text}")
                return False, {
                    "error": f"Грешка от Anthropic API: {response.status_code}",
                    "details": response.text
                }
            
            # Обработваме отговора
            result = response.json()
            
            # Извличаме текстовия отговор
            if "content" in result and len(result["content"]) > 0:
                content = result["content"][0].get("text", "")
                
                # Опитваме се да извлечем JSON от отговора
                try:
                    # Намираме началото и края на JSON обекта
                    start_idx = content.find('{')
                    end_idx = content.rfind('}') + 1
                    
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        analysis_result = json.loads(json_str)
                        
                        # Добавяме метаданни
                        analysis_result["analysis_time"] = elapsed_time
                        analysis_result["full_analysis"] = content
                        
                        logger.info(f"Успешен анализ за позиция {position_id}: {analysis_result}")
                        return True, analysis_result
                    else:
                        logger.error(f"Не е намерен валиден JSON в отговора за позиция {position_id}: {content}")
                        return False, {"error": "Не е намерен валиден JSON в отговора", "raw_response": content}
                except Exception as e:
                    logger.error(f"Грешка при обработка на JSON за позиция {position_id}: {e}")
                    return False, {"error": f"Грешка при обработка на JSON: {e}", "raw_response": content}
            else:
                logger.error(f"Празен отговор от Anthropic API за позиция {position_id}")
                return False, {"error": "Празен отговор от Anthropic API", "raw_response": result}
    
    except Exception as e:
        logger.error(f"Неочаквана грешка при анализ на изображението за позиция {position_id}: {e}")
        return False, {"error": f"Неочаквана грешка: {e}"}

async def analyze_position(position_id: int) -> PositionAnalysisResult:
    """
    Анализира изображение от определена позиция
    
    Args:
        position_id: ID на позицията
    
    Returns:
        PositionAnalysisResult обект с резултата от анализа
    """
    # Определяме пътя до изображението
    ptz_config = get_ptz_capture_config()
    position_dir = os.path.join(ptz_config.save_dir, f"position_{position_id}")
    image_path = os.path.join(position_dir, "latest.jpg")
    
    # Създаваме начален обект за резултата
    result = PositionAnalysisResult(
        position_id=position_id,
        timestamp=datetime.now()
    )
    
    try:
        # Проверяваме дали изображението съществува
        if not os.path.exists(image_path):
            logger.error(f"Изображението за позиция {position_id} не съществува: {image_path}")
            result.weather_conditions = f"Няма налично изображение за позиция {position_id}"
            return result
        
        # Четем изображението
        image_data = await download_image(image_path)
        
        if not image_data:
            logger.error(f"Не може да се прочете изображението за позиция {position_id}: {image_path}")
            result.weather_conditions = f"Не може да се прочете изображението за позиция {position_id}"
            return result
        
        # Анализираме изображението
        success, analysis = await analyze_image_with_anthropic(image_data, position_id)
        
        if not success:
            logger.error(f"Грешка при анализ на изображението за позиция {position_id}: {analysis.get('error', 'Unknown error')}")
            result.weather_conditions = f"Грешка при анализ за позиция {position_id}: {analysis.get('error', 'Unknown error')}"
            return result
        
        # Обновяваме резултата с данните от анализа
        result.cloud_coverage = float(analysis.get("cloud_coverage", 0))
        result.cloud_type = analysis.get("cloud_type", "")
        result.weather_conditions = analysis.get("weather_conditions", "")
        result.confidence = float(analysis.get("confidence", 0))
        result.analysis_time = float(analysis.get("analysis_time", 0))
        result.full_analysis = analysis.get("full_analysis", "")
        result.raw_response = analysis
        
        logger.info(f"Успешен анализ за позиция {position_id}: {result.weather_conditions} (облачност: {result.cloud_coverage}%)")
        
        return result
    
    except Exception as e:
        logger.error(f"Неочаквана грешка при анализ за позиция {position_id}: {e}")
        result.weather_conditions = f"Неочаквана грешка: {str(e)}"
        return result

def calculate_overall_result(position_results: Dict[int, PositionAnalysisResult]) -> Dict[str, Any]:
    """
    Изчислява обобщения резултат от анализите на всички позиции
    
    Args:
        position_results: Речник с резултати по позиции
    
    Returns:
        Dict с обобщения резултат
    """
    # Изчисляваме средната облачност от валидните резултати
    valid_cloud_results = [r.cloud_coverage for r in position_results.values() 
                         if r.cloud_coverage > 0 and r.confidence > 0]
    
    avg_cloud_coverage = sum(valid_cloud_results) / len(valid_cloud_results) if valid_cloud_results else 0
    
    # Определяме дали има слънце на някоя от позициите
    sunny = False
    for result in position_results.values():
        if result.raw_response and result.raw_response.get("is_sunny", False):
            sunny = True
            break
    
    # Определяме преобладаващите типове облаци
    cloud_types = {}
    for result in position_results.values():
        if result.cloud_type:
            cloud_types[result.cloud_type] = cloud_types.get(result.cloud_type, 0) + 1
    
    dominant_cloud_type = max(cloud_types.items(), key=lambda x: x[1])[0] if cloud_types else ""
    
    # Съставяме обобщено описание на времето
    if avg_cloud_coverage < 10:
        if sunny:
            overall_conditions = "Ясно време със слънце"
        else:
            overall_conditions = "Ясно време"
    elif avg_cloud_coverage < 30:
        if sunny:
            overall_conditions = f"Предимно ясно със слаба облачност ({dominant_cloud_type})"
        else:
            overall_conditions = f"Предимно ясно със слаба облачност ({dominant_cloud_type})"
    elif avg_cloud_coverage < 70:
        if sunny:
            overall_conditions = f"Променлива облачност ({dominant_cloud_type}) със слънчеви периоди"
        else:
            overall_conditions = f"Променлива облачност ({dominant_cloud_type})"
    elif avg_cloud_coverage < 90:
        overall_conditions = f"Предимно облачно ({dominant_cloud_type})"
    else:
        overall_conditions = f"Плътна облачност ({dominant_cloud_type})"
    
    # Добавяме информация за видимостта
    visibility_counts = {"отлична": 0, "добра": 0, "умерена": 0, "лоша": 0}
    
    for result in position_results.values():
        if result.raw_response and "visibility" in result.raw_response:
            visibility = result.raw_response["visibility"].lower()
            if visibility in visibility_counts:
                visibility_counts[visibility] += 1
    
    max_visibility = max(visibility_counts.items(), key=lambda x: x[1])[0] if any(visibility_counts.values()) else "неизвестна"
    
    if max_visibility != "неизвестна":
        overall_conditions += f", видимост: {max_visibility}"
    
    # Изчисляваме общото време за анализ
    total_analysis_time = sum(r.analysis_time for r in position_results.values())
    
    return {
        "avg_cloud_coverage": avg_cloud_coverage,
        "overall_weather_conditions": overall_conditions,
        "sunny": sunny,
        "total_analysis_time": total_analysis_time
    }

async def perform_multi_image_analysis() -> MultiAnalysisResult:
    """
    Изпълнява целия процес на анализ на изображения от всички позиции
    
    Returns:
        MultiAnalysisResult обект с резултата от анализа
    """
    config = get_analysis_config()
    ptz_config = get_ptz_capture_config()
    
    # Създаваме начален обект за резултата
    result = MultiAnalysisResult(
        timestamp=datetime.now()
    )
    
    try:
        # Проверяваме дали имаме завършен цикъл на прихващане
        if not ptz_config.last_complete_cycle_time:
            logger.warning("Няма завършен цикъл на прихващане, анализът се пропуска")
            result.overall_weather_conditions = "Няма завършен цикъл на прихващане"
            update_analysis_config(status="warning")
            return result
        
        # Анализираме всяка позиция
        position_results = {}
        
        for position_id in ptz_config.positions:
            position_result = await analyze_position(position_id)
            position_results[position_id] = position_result
        
        # Добавяме резултатите към общия резултат
        result.position_results = position_results
        
        # Изчисляваме обобщения резултат
        overall = calculate_overall_result(position_results)
        
        # Обновяваме резултата с обобщените данни
        result.avg_cloud_coverage = overall["avg_cloud_coverage"]
        result.overall_weather_conditions = overall["overall_weather_conditions"]
        result.sunny = overall["sunny"]
        result.total_analysis_time = overall["total_analysis_time"]
        
        # Обновяваме статуса
        update_analysis_config(status="ok")
        
        logger.info(f"Успешен мулти-анализ: {result.overall_weather_conditions} (средна облачност: {result.avg_cloud_coverage}%)")
        
        return result
    
    except Exception as e:
        logger.error(f"Неочаквана грешка при мулти-анализ: {e}")
        result.overall_weather_conditions = f"Неочаквана грешка: {str(e)}"
        update_analysis_config(status="error")
        return result

def run_async_analysis():
    """Изпълнява асинхронен анализ в синхронен контекст"""
    try:
        return asyncio.run(perform_multi_image_analysis())
    except RuntimeError as e:
        if "There is no current event loop in thread" in str(e):
            # Създаваме нов event loop и го използваме
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(perform_multi_image_analysis())
            finally:
                loop.close()
        else:
            # Ако е друга RuntimeError, вдигаме я нагоре
            raise

def analysis_loop():
    """Основен цикъл за периодичен анализ на изображения"""
    config = get_analysis_config()
    
    while config.running:
        try:
            # Изпълняваме анализ
            result = run_async_analysis()
            
            # Добавяме резултата в историята
            add_analysis_result(result)
            
        except Exception as e:
            logger.error(f"Неочаквана грешка в analysis_loop: {e}")
        
        # Обновяваме конфигурацията (за случай, че е променена)
        config = get_analysis_config()
        
        # Спим до следващия анализ
        time.sleep(config.analysis_interval)

def start_analysis_thread():
    """Стартира фонов процес за анализ на изображения"""
    global analysis_thread
    
    if analysis_thread is None or not analysis_thread.is_alive():
        analysis_thread = threading.Thread(target=analysis_loop)
        analysis_thread.daemon = True
        analysis_thread.start()
        logger.info("Multi Image Analysis thread started")
        return True
    
    return False

def stop_analysis_thread():
    """Спира фоновия процес за анализ на изображения"""
    update_analysis_config(running=False)
    logger.info("Multi Image Analysis thread stopping")
    return True

async def analyze_images_now() -> MultiAnalysisResult:
    """Принудително изпълнява анализ на изображения веднага"""
    result = await perform_multi_image_analysis()
    add_analysis_result(result)
    return result

# Функция за инициализиране на модула
def initialize():
    """Инициализира модула"""
    # Проверяваме дали имаме API ключ
    api_key = get_anthropic_api_key()
    if not api_key:
        logger.error("ANTHROPIC_API_KEY не е наличен - Multi Image Analysis модулът не може да бъде инициализиран")
        update_analysis_config(status="error")
        return False
    
    # Логваме къде се очаква да бъдат изображенията
    ptz_config = get_ptz_capture_config()
    logger.info(f"Модулът ще анализира изображения от: {ptz_config.save_dir}")
    
    # Стартираме thread за анализ
    start_analysis_thread()
    logger.info("Multi Image Analysis модул инициализиран успешно")
    return True

# Автоматично инициализиране при import
initialize()