"""
Логика за анализ на изображения с помощта на Anthropic API
"""

import os
import json
import time
import threading
import httpx
from datetime import datetime
from io import BytesIO
from PIL import Image
from typing import Dict, Any, Optional, Tuple
import base64
import asyncio

from .config import (
    get_analysis_config, 
    update_analysis_config, 
    add_analysis_result,
    AnalysisResult
)
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("image_analyzer")

# Глобални променливи
analysis_thread = None

def get_anthropic_api_key() -> Optional[str]:
    """
    Взима Anthropic API ключа от средата на Hugging Face
    
    Hugging Face съхранява секретите като environment променливи,
    така че можем да ги достъпим безопасно.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY не е наличен! Моля, добавете го като секрет в Hugging Face.")
        return None
    return api_key

async def download_image(url: str) -> Optional[bytes]:
    """Чете изображение от локален файл или URL"""
    try:
        # Проверяваме дали URL е локален път
        if not url.startswith(('http://', 'https://')):
            # Това е локален път, опитваме да го прочетем директно
            # Проверяваме няколко възможни пътища
            paths_to_try = [
                url,  # Оригиналния път
                os.path.join("/app", url),  # В case на Docker среда
                os.path.join(os.getcwd(), url)  # Относително от текущата директория
            ]
            
            for path in paths_to_try:
                if os.path.exists(path):
                    logger.info(f"Четене на изображение от локален файл: {path}")
                    try:
                        with open(path, "rb") as f:
                            image_data = f.read()
                        logger.info(f"Успешно прочетено изображение от {path}, размер: {len(image_data)} bytes")
                        
                        # Проверяваме дали изображението е валидно
                        try:
                            Image.open(BytesIO(image_data))
                            return image_data
                        except Exception as e:
                            logger.error(f"Невалидно изображение от {path}: {e}")
                            continue  # Опитваме със следващия път
                    except Exception as e:
                        logger.error(f"Грешка при четене на локален файл {path}: {e}")
                        continue  # Опитваме със следващия път
            
            # Ако стигнем дотук, не сме намерили валиден файл
            logger.error(f"Не може да се намери или прочете локален файл: {url}")
            logger.error(f"Опитани пътища: {paths_to_try}")
            return None
            
        else:
            # Това е URL, използваме HTTP заявка
            logger.info(f"Опит за изтегляне на изображение от URL: {url}")
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0, follow_redirects=True)
                
                if response.status_code != 200:
                    logger.error(f"Грешка при изтегляне на изображението: HTTP {response.status_code}")
                    return None
                
                image_data = response.content
                logger.info(f"Успешно изтеглено изображение от URL, размер: {len(image_data)} bytes")
                
                # Проверяваме дали изображението е валидно
                try:
                    Image.open(BytesIO(image_data))
                    return image_data
                except Exception as e:
                    logger.error(f"Невалидно изображение от URL: {e}")
                    return None
    except Exception as e:
        logger.error(f"Грешка при изтегляне/четене на изображението: {e}")
        return None

def encode_image_base64(image_data: bytes) -> str:
    """Кодира изображението в base64"""
    return base64.b64encode(image_data).decode('utf-8')

async def analyze_image_with_anthropic(image_data: bytes) -> Tuple[bool, Dict[str, Any]]:
    """
    Анализира изображение с помощта на Anthropic API
    
    Args:
        image_data: Байтове на изображението
    
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
        
        # Изграждаме съобщение за Claude
        prompt = """
        Ти си експерт метеоролог, който анализира изображения от камери. Анализирай предоставеното изображение и дай детайлна информация за:
        
        1. Процент облачност (0-100%)
        2. Тип на облаците (ако има такива)
        3. Видимост (отлична, добра, умерена, лоша)
        4. Общо описание на метеорологичните условия в момента
        5. Отговори на български език
        6. Анализите между 21:00 и 06:00 българско време ги отбелязвай като: Анализа се извършва в светлата част на деня!
        
        Отговори в следния JSON формат:
        {
          "cloud_coverage": [число от 0 до 100],
          "cloud_type": "[тип на облаците, например: кумулус, стратус, нимбостратус и т.н.]",
          "visibility": "[отлична/добра/умерена/лоша]",
          "weather_conditions": "[кратко описание на метеорологичните условия]",
          "confidence": [число от 0 до 100, показващо твоята увереност в анализа]
        }
        
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
        
        logger.info(f"Изпращане на заявка към Anthropic API с модел {config.anthropic_model}")
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
            logger.info(f"Получен отговор от Anthropic API за {elapsed_time:.2f} секунди")
            
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
                        
                        logger.info(f"Успешен анализ: {analysis_result}")
                        return True, analysis_result
                    else:
                        logger.error(f"Не е намерен валиден JSON в отговора: {content}")
                        return False, {"error": "Не е намерен валиден JSON в отговора", "raw_response": content}
                except Exception as e:
                    logger.error(f"Грешка при обработка на JSON: {e}")
                    return False, {"error": f"Грешка при обработка на JSON: {e}", "raw_response": content}
            else:
                logger.error("Празен отговор от Anthropic API")
                return False, {"error": "Празен отговор от Anthropic API", "raw_response": result}
    
    except Exception as e:
        logger.error(f"Неочаквана грешка при анализ на изображението: {e}")
        return False, {"error": f"Неочаквана грешка: {e}"}

async def perform_image_analysis() -> AnalysisResult:
    """
    Изпълнява целия процес на анализ на изображение
    
    Returns:
        AnalysisResult обект с резултата от анализа
    """
    config = get_analysis_config()
    
    # Създаваме начален обект за резултата
    result = AnalysisResult(
        timestamp=datetime.now()
    )
    
    try:
        # Изтегляме/четем изображението
        image_data = await download_image(config.image_url)
        
        if not image_data:
            logger.error(f"Не може да се прочете/изтегли изображение от {config.image_url}")
            result.weather_conditions = "Не може да се прочете/изтегли изображение"
            update_analysis_config(status="error")
            return result
        
        # Анализираме изображението
        success, analysis = await analyze_image_with_anthropic(image_data)
        
        if not success:
            logger.error(f"Грешка при анализ на изображението: {analysis.get('error', 'Unknown error')}")
            result.weather_conditions = f"Грешка при анализ: {analysis.get('error', 'Unknown error')}"
            update_analysis_config(status="error")
            return result
        
        # Обновяваме резултата с данните от анализа
        result.cloud_coverage = float(analysis.get("cloud_coverage", 0))
        result.cloud_type = analysis.get("cloud_type", "")
        result.weather_conditions = analysis.get("weather_conditions", "")
        result.confidence = float(analysis.get("confidence", 0))
        result.analysis_time = float(analysis.get("analysis_time", 0))
        result.full_analysis = analysis.get("full_analysis", "")
        result.raw_response = analysis
        
        # Обновяваме статуса
        update_analysis_config(status="ok")
        
        logger.info(f"Успешен анализ: {result.weather_conditions} (облачност: {result.cloud_coverage}%, тип: {result.cloud_type})")
        
        return result
    
    except Exception as e:
        logger.error(f"Неочаквана грешка при анализ: {e}")
        result.weather_conditions = f"Неочаквана грешка: {str(e)}"
        update_analysis_config(status="error")
        return result

def run_async_analysis():
    """Изпълнява асинхронен анализ в синхронен контекст"""
    try:
        return asyncio.run(perform_image_analysis())
    except RuntimeError as e:
        if "There is no current event loop in thread" in str(e):
            # Създаваме нов event loop и го използваме
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(perform_image_analysis())
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
        logger.info("Analysis thread started")
        return True
    
    return False

def stop_analysis_thread():
    """Спира фоновия процес за анализ на изображения"""
    update_analysis_config(running=False)
    logger.info("Analysis thread stopping")
    return True

async def analyze_image_now() -> AnalysisResult:
    """Принудително изпълнява анализ на изображение веднага"""
    result = await perform_image_analysis()
    add_analysis_result(result)
    return result

# Функция за инициализиране на модула
def initialize():
    """Инициализира модула"""
    # Проверяваме дали имаме API ключ
    api_key = get_anthropic_api_key()
    if not api_key:
        logger.error("ANTHROPIC_API_KEY не е наличен - Image Analysis модулът не може да бъде инициализиран")
        update_analysis_config(status="error")
        return False
    
    # Логваме къде се очаква да бъде изображението
    config = get_analysis_config()
    logger.info(f"Модулът ще анализира изображения от: {config.image_url}")
    
    # Проверяваме дали файла съществува в момента
    if not config.image_url.startswith(('http://', 'https://')):
        paths_to_try = [
            config.image_url,
            os.path.join("/app", config.image_url),
            os.path.join(os.getcwd(), config.image_url)
        ]
        
        file_exists = False
        for path in paths_to_try:
            if os.path.exists(path):
                logger.info(f"Изображението съществува на път: {path}")
                file_exists = True
                break
                
        if not file_exists:
            logger.warning(f"Изображението не съществува в нито един от опитаните пътища: {paths_to_try}")
            logger.warning("Модулът ще работи, но първоначалният анализ може да се провали")
    
    # Стартираме thread за анализ
    start_analysis_thread()
    logger.info("Image Analysis модул инициализиран успешно")
    return True

# Автоматично инициализиране при import
initialize()