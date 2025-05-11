# Файл: modules/ptz_simple/controller.py
"""
Контролер за PTZ камерата чрез ONVIF - опростена имплементация
"""

import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from onvif import ONVIFCamera
import zeep

from .config import get_ptz_config, update_ptz_config
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_simple_controller")

# Фиксиране на известен проблем със zeep библиотеката
def zeep_pythonvalue(self, xmlvalue):
    return xmlvalue

zeep.xsd.simple.AnySimpleType.pythonvalue = zeep_pythonvalue

# Глобални променливи
cam = None
ptz = None
media = None
profile_token = None

async def initialize_camera() -> bool:
    """
    Асинхронно инициализира камерата чрез ONVIF
    
    Returns:
        bool: Успешна инициализация или не
    """
    global cam, ptz, media, profile_token
    
    config = get_ptz_config()
    
    try:
        logger.info(f"Инициализиране на ONVIF камера: {config.camera_ip}:{config.camera_port}")
        
        # Създаваме ONVIF камера
        cam = ONVIFCamera(config.camera_ip, config.camera_port, config.username, config.password)
        
        # Създаваме media service
        media = cam.create_media_service()
        
        # Получаваме профилите
        profiles = media.GetProfiles()
        
        if not profiles:
            logger.error("Не са намерени профили в камерата")
            update_ptz_config(status="error")
            return False
            
        # Вземаме първия профил
        profile_token = profiles[0].token
        logger.info(f"Използваме профил: {profile_token}")
        
        # Създаваме ptz service
        ptz = cam.create_ptz_service()
        
        # Обновяваме пресет токените
        await async_update_preset_tokens()
        
        # Обновяваме статуса
        update_ptz_config(status="ok")
        
        logger.info("ONVIF камера инициализирана успешно")
        return True
    except Exception as e:
        logger.error(f"Грешка при инициализиране на ONVIF камера: {str(e)}")
        update_ptz_config(status="error")
        return False

def initialize_camera_sync() -> bool:
    """
    Инициализира камерата чрез ONVIF (синхронен метод)
    
    Returns:
        bool: Успешна инициализация или не
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(initialize_camera())
    finally:
        loop.close()

async def async_get_presets() -> Dict[str, Dict[str, Any]]:
    """
    Асинхронно получава списък с пресети от камерата
    
    Returns:
        Dict[str, Dict[str, Any]]: Речник с пресети
    """
    global ptz, profile_token
    
    if not ptz or not profile_token:
        success = await initialize_camera()
        if not success:
            return {}
    
    try:
        # Получаваме пресетите
        logger.info("Получаване на пресети от камерата")
        presets = ptz.GetPresets({'ProfileToken': profile_token})
        
        # Обработваме пресетите в подходящ формат
        result = {}
        for preset in presets:
            # Различните камери могат да имат различна структура на пресетите
            # Поддържаме и двата формата
            preset_token = preset.get('token') or preset.get('PresetToken')
            preset_name = preset.get('Name', f"Preset {preset_token}")
            
            result[preset_token] = {
                'name': preset_name,
                'token': preset_token
            }
            
        logger.info(f"Успешно получени {len(result)} пресета")
        return result
    except Exception as e:
        logger.error(f"Грешка при получаване на пресети: {str(e)}")
        return {}

def get_presets() -> Dict[str, Dict[str, Any]]:
    """
    Получава списък с пресети от камерата (синхронен метод)
    
    Returns:
        Dict[str, Dict[str, Any]]: Речник с пресети
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_get_presets())
    finally:
        loop.close()

async def async_update_preset_tokens() -> bool:
    """
    Асинхронно обновява мапинга между нашите позиции и реалните пресет токени
    
    Returns:
        bool: Успешно обновяване или не
    """
    presets = await async_get_presets()
    
    if not presets:
        logger.warning("Не са намерени пресети, мапингът не е обновен")
        return False
    
    # Тук правим предположения за мапинга между нашите позиции (0-4)
    # и реалните ONVIF пресети. Обикновено се опитваме да съпоставим по имена.
    
    # Начин 1: Опитваме се да напаснем по имена
    position_names = {
        0: ["home", "default", "покой", "позиция 0", "position 0", "preset 0"],
        1: ["east", "изток", "позиция 1", "position 1", "preset 1"],
        2: ["west", "запад", "позиция 2", "position 2", "preset 2"],
        3: ["north", "север", "позиция 3", "position 3", "preset 3"],
        4: ["south", "юг", "позиция 4", "position 4", "preset 4"]
    }
    
    preset_tokens = {}
    
    # Първо опитваме да напаснем по имена
    for preset_token, preset_data in presets.items():
        preset_name = preset_data['name'].lower()
        
        for position_id, name_keywords in position_names.items():
            if any(keyword in preset_name for keyword in name_keywords):
                preset_tokens[position_id] = preset_token
                break
    
    # Начин 2: Ако не намерим съответствия, просто използваме пресетите по ред
    if not preset_tokens and len(presets) >= 5:
        preset_list = list(presets.keys())
        for i in range(min(5, len(preset_list))):
            preset_tokens[i] = preset_list[i]
    
    # Начин 3: Ако все още нямаме съпоставка, използваме ONVIF индексите
    # Някои камери използват числови индекси директно като токени
    if not preset_tokens:
        for preset_token in presets.keys():
            try:
                # Опитваме се да конвертираме токена към число
                position_id = int(preset_token)
                if 0 <= position_id <= 4:
                    preset_tokens[position_id] = preset_token
            except (ValueError, TypeError):
                continue
    
    # Обновяваме конфигурацията с мапинга
    if preset_tokens:
        logger.info(f"Обновен мапинг на пресет токени: {preset_tokens}")
        update_ptz_config(preset_tokens=preset_tokens)
        return True
    else:
        logger.warning("Не са намерени съответствия между позиции и пресети")
        return False

def update_preset_tokens() -> bool:
    """
    Обновява мапинга между нашите позиции и реалните пресет токени (синхронен метод)
    
    Returns:
        bool: Успешно обновяване или не
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_update_preset_tokens())
    finally:
        loop.close()

async def async_move_to_position(position_id: int) -> bool:
    """
    Асинхронно премества камерата към предварително зададена позиция
    
    Args:
        position_id: ID на позицията (0-4)
        
    Returns:
        bool: Успешно преместване или не
    """
    global ptz, profile_token
    
    config = get_ptz_config()
    
    if not ptz or not profile_token:
        success = await initialize_camera()
        if not success:
            return False
    
    # Проверяваме дали позицията е валидна
    if position_id not in config.positions:
        logger.error(f"Невалидна позиция: {position_id}")
        return False
    
    # Проверяваме дали имаме токен за тази позиция
    preset_token = config.preset_tokens.get(position_id)
    if not preset_token:
        logger.warning(f"Не е намерен пресет токен за позиция {position_id}, опитваме да обновим маппинга")
        
        # Опитваме се да обновим токените
        await async_update_preset_tokens()
        
        # Проверяваме отново
        config = get_ptz_config()
        preset_token = config.preset_tokens.get(position_id)
        
        if not preset_token:
            logger.error(f"Не е намерен пресет токен за позиция {position_id}")
            return False
    
    try:
        # Преместване към пресет
        position_name = config.positions[position_id].get("name", f"Позиция {position_id}")
        logger.info(f"Преместване към позиция {position_id} ({position_name}), пресет токен: {preset_token}")
        
        ptz.GotoPreset({
            'ProfileToken': profile_token,
            'PresetToken': preset_token,
            'Speed': {
                'PanTilt': {'x': config.move_speed, 'y': config.move_speed},
                'Zoom': {'x': config.move_speed}
            }
        })
        
        # Обновяваме информацията за текущата позиция
        update_ptz_config(
            current_position=position_id,
            last_move_time=datetime.now()
        )
        
        logger.info(f"Успешно преместване към позиция {position_id}")
        return True
    except Exception as e:
        logger.error(f"Грешка при преместване към позиция {position_id}: {str(e)}")
        return False

def move_to_position(position_id: int) -> bool:
    """
    Премества камерата към предварително зададена позиция (синхронен метод)
    
    Args:
        position_id: ID на позицията (0-4)
        
    Returns:
        bool: Успешно преместване или не
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_move_to_position(position_id))
    finally:
        loop.close()

async def async_stop_movement() -> bool:
    """
    Асинхронно спира движението на камерата
    
    Returns:
        bool: Успешно спиране или не
    """
    global ptz, profile_token
    
    if not ptz or not profile_token:
        success = await initialize_camera()
        if not success:
            return False
    
    try:
        logger.info("Спиране на движението на камерата")
        
        ptz.Stop({
            'ProfileToken': profile_token,
            'PanTilt': True,
            'Zoom': True
        })
        
        logger.info("Движението на камерата е спряно успешно")
        return True
    except Exception as e:
        logger.error(f"Грешка при спиране на движението: {str(e)}")
        return False

def stop_movement() -> bool:
    """
    Спира движението на камерата (синхронен метод)
    
    Returns:
        bool: Успешно спиране или не
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_stop_movement())
    finally:
        loop.close()

def get_current_position() -> Dict[str, Any]:
    """
    Връща информация за текущата позиция
    
    Returns:
        Dict[str, Any]: Информация за текущата позиция
    """
    config = get_ptz_config()
    
    current_position = config.current_position
    position_data = config.positions.get(current_position, {})
    
    return {
        "position_id": current_position,
        "position_name": position_data.get("name", f"Позиция {current_position}"),
        "position_description": position_data.get("description", ""),
        "last_move_time": config.last_move_time,
        "preset_token": config.preset_tokens.get(current_position)
    }

def run_diagnostics() -> Dict[str, Any]:
    """
    Изпълнява диагностика на PTZ функционалността
    
    Returns:
        Dict[str, Any]: Резултати от диагностиката
    """
    results = {
        "camera_connection": False,
        "presets_available": 0,
        "position_mapping": {},
        "error": None
    }
    
    try:
        # Проверка на връзката с камерата
        if initialize_camera_sync():
            results["camera_connection"] = True
            
            # Получаване на пресети
            presets = get_presets()
            results["presets_available"] = len(presets)
            
            # Обновяване на мапинга
            update_preset_tokens()
            
            # Добавяне на информация за мапинга
            config = get_ptz_config()
            for position_id, preset_token in config.preset_tokens.items():
                # Намираме името на пресета
                preset_name = None
                if preset_token in presets:
                    preset_name = presets[preset_token].get("name")
                
                results["position_mapping"][position_id] = {
                    "position_name": config.positions.get(position_id, {}).get("name", f"Позиция {position_id}"),
                    "preset_token": preset_token,
                    "preset_name": preset_name
                }
    except Exception as e:
        results["error"] = str(e)
    
    return results

def initialize() -> bool:
    """
    Инициализира модула
    
    Returns:
        bool: Успешна инициализация или не
    """
    success = initialize_camera_sync()
    
    if success:
        logger.info("PTZ Simple модул инициализиран успешно")
    else:
        logger.error("Грешка при инициализиране на PTZ Simple модул")
    
    return success

# Автоматично инициализиране при импорт
initialize()