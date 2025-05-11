# Файл: modules/ptz_control/controller.py
"""
Логика за контрол на PTZ камера чрез Imou Life API
"""

import time
import threading
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# Импортиране на imouapi и aiohttp за сесията
import aiohttp
from imouapi.api import ImouAPIClient
from imouapi.device import ImouDevice
# В по-старите версии на imouapi, ImouAPIException може да не съществува
# Ще използваме стандартен Exception

from .config import get_ptz_config, update_ptz_config
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_controller")

# Глобални променливи
api_client = None
imou_device = None

# Функция за изпълнение на асинхронен код синхронно
def run_async(coro):
    """Изпълнява асинхронна функция в синхронен контекст"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Ако нямаме event loop в текущата нишка, създаваме нов
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)

async def async_initialize_camera() -> bool:
    """
    Асинхронно инициализира Imou устройството
    
    Returns:
        bool: Успешна инициализация или не
    """
    global api_client, imou_device
    
    config = get_ptz_config()
    
    try:
        logger.info(f"Свързване с Imou API, устройство SN: {config.device_serial_number}")
        
        # Създаваме aiohttp сесия (задължителна за imouapi 1.0.13)
        session = aiohttp.ClientSession()
        
        # Създаваме API клиент със сесия
        api_client = ImouAPIClient(config.app_id, config.app_secret, session)
        
        # Създаваме устройство
        imou_device = ImouDevice(api_client, config.device_serial_number)
        
        # Проверяваме връзката с устройството
        device_info = await imou_device.get_device_info()
        
        if device_info:
            logger.info(f"Успешно свързване с Imou устройство: {device_info.name}")
            update_ptz_config(status="ok")
            
            # Няма нужда да затваряме сесията - тя ще се използва от методите по-късно
            # Глобалния клиент и устройство ще използват тази сесия
            
            return True
        else:
            logger.error("Не може да се получи информация за устройството")
            update_ptz_config(status="error")
            await session.close()  # Затваряме сесията при грешка
            return False
            
    except Exception as e:
        logger.error(f"Грешка при свързване с Imou устройство: {str(e)}")
        update_ptz_config(status="error")
        try:
            if 'session' in locals():
                await session.close()  # Затваряме сесията, ако съществува
        except:
            pass
        return False

def initialize_camera() -> bool:
    """
    Инициализира връзка с PTZ камерата
    
    Returns:
        bool: Успешна инициализация или не
    """
    return run_async(async_initialize_camera())

async def async_move_to_position(position_id: int) -> bool:
    """
    Асинхронно премества камерата към предварително зададена позиция
    
    Args:
        position_id: ID на позицията (0-4)
        
    Returns:
        bool: Успешно преместване или не
    """
    global imou_device
    
    config = get_ptz_config()
    
    # Проверяваме дали устройството е инициализирано
    if not imou_device:
        logger.error("Imou устройството не е инициализирано")
        return False
    
    # Проверяваме дали позицията съществува
    if position_id not in config.positions:
        logger.error(f"Невалидна позиция: {position_id}")
        return False
    
    try:
        # Конвертираме нашата позиция към Imou пресет (1-5 вместо 0-4)
        preset_id = position_id + 1
        
        logger.info(f"Преместване към preset {preset_id} (позиция {position_id}: {config.positions[position_id]['name']})")
        
        # Извикваме Imou API за преместване към пресет
        await imou_device.go_to_preset(preset_id)
        
        # Обновяваме информацията за текущата позиция
        update_ptz_config(
            current_position=position_id,
            last_move_time=datetime.now()
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Грешка при преместване към позиция {position_id}: {str(e)}")
        return False

def move_to_position(position_id: int) -> bool:
    """
    Премества камерата към предварително зададена позиция
    
    Args:
        position_id: ID на позицията (0-4)
        
    Returns:
        bool: Успешно преместване или не
    """
    return run_async(async_move_to_position(position_id))

async def async_stop_movement() -> bool:
    """
    Асинхронно спира текущото движение на камерата
    
    Returns:
        bool: Успешно спиране или не
    """
    global imou_device
    
    if not imou_device:
        logger.error("Imou устройството не е инициализирано")
        return False
    
    try:
        await imou_device.stop_ptz_movement()
        logger.info("Камерата е спряна")
        return True
        
    except Exception as e:
        logger.error(f"Грешка при спиране на камерата: {str(e)}")
        return False

def stop_movement() -> bool:
    """
    Спира текущото движение на камерата
    
    Returns:
        bool: Успешно спиране или не
    """
    return run_async(async_stop_movement())

async def async_get_current_position() -> Dict[str, Any]:
    """
    Асинхронно връща текущата позиция на камерата
    
    Returns:
        Dict: Информация за текущата позиция
    """
    global imou_device
    
    config = get_ptz_config()
    
    if not imou_device:
        logger.error("Imou устройството не е инициализирано")
        return {"error": "Imou устройството не е инициализирано"}
    
    try:
        # imouapi не поддържа директно получаване на текуща позиция
        # връщаме информация базирана на последното известно преместване
        
        return {
            "position_id": config.current_position,
            "position_name": config.positions[config.current_position]['name'],
            "last_move_time": config.last_move_time.isoformat() if config.last_move_time else None
        }
        
    except Exception as e:
        logger.error(f"Грешка при получаване на текущата позиция: {str(e)}")
        return {"error": str(e)}

def get_current_position() -> Dict[str, Any]:
    """
    Връща текущата позиция на камерата
    
    Returns:
        Dict: Информация за текущата позиция
    """
    return run_async(async_get_current_position())

def initialize() -> bool:
    """
    Инициализира PTZ контрол модула
    
    Returns:
        bool: Успешна инициализация или не
    """
    success = initialize_camera()
    
    if success:
        logger.info("PTZ контрол модул с Imou API инициализиран успешно")
    else:
        logger.error("Грешка при инициализиране на PTZ контрол модул чрез Imou API")
    
    return success

# Автоматично инициализиране при импорт
initialize()