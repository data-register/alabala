# Файл: modules/ptz_control/controller.py
"""
Логика за контрол на PTZ камера чрез Imou Life API
"""

import time
import threading
import asyncio
import inspect
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# Импортиране на imouapi и aiohttp за сесията
import aiohttp
from imouapi.api import ImouAPIClient
from imouapi.device import ImouDevice

from .config import get_ptz_config, update_ptz_config
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_controller")

# Глобални променливи
api_client = None
imou_device = None
api_session = None

# Функция за изпълнение на асинхронен код синхронно
def run_async(coro):
    """
    Изпълнява асинхронна функция в синхронен контекст
    При FastAPI, Event Loop вече съществува, трябва да бъдем внимателни
    """
    try:
        # Проверяваме дали вече сме в асинхронен контекст
        if asyncio.iscoroutinefunction(inspect.currentframe().f_back.f_code):
            logger.warning("run_async е извикан от асинхронна функция - това не е препоръчително")
            # Връщаме корутината, за да се обработи по-късно с await
            return coro
            
        # Проверка за съществуващ event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Ако loop вече работи, създаваме нов loop за този конкретен случай
                new_loop = asyncio.new_event_loop()
                result = new_loop.run_until_complete(coro)
                new_loop.close()
                return result
        except RuntimeError:
            # Ако нямаме event loop, създаваме нов
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Изпълняваме корутината в текущия event loop
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Грешка в run_async: {str(e)}")
        # Връщаме None вместо да хвърляме изключение
        return None

# Опитваме се да извлечем информация за API от imouapi библиотеката
def get_available_methods():
    """Връща списък с достъпните методи в imouapi"""
    global imou_device
    
    if not imou_device:
        return []
    
    try:
        methods = [m for m in dir(imou_device) if callable(getattr(imou_device, m)) and not m.startswith('_')]
        logger.info(f"Намерени методи в imouDevice: {methods}")
        return methods
    except Exception as e:
        logger.error(f"Грешка при получаване на методи: {str(e)}")
        return []

async def async_initialize_camera() -> bool:
    """
    Асинхронно инициализира Imou устройството
    
    Returns:
        bool: Успешна инициализация или не
    """
    global api_client, imou_device, api_session
    
    config = get_ptz_config()
    
    try:
        logger.info(f"Свързване с Imou API, устройство SN: {config.device_serial_number}")
        
        # Създаваме aiohttp сесия
        api_session = aiohttp.ClientSession()
        
        # Създаваме API клиент със сесия
        api_client = ImouAPIClient(config.app_id, config.app_secret, api_session)
        
        # Създаваме устройство
        imou_device = ImouDevice(api_client, config.device_serial_number)
        
        # Проверяваме какви методи имаме на разположение
        methods = get_available_methods()
        logger.info(f"Достъпни методи в imouapi: {methods}")
        
        # Проверяваме дали имаме PTZ методи
        has_ptz_methods = any(m for m in methods if 'ptz' in m.lower() or 'preset' in m.lower())
        logger.info(f"Камерата {'има' if has_ptz_methods else 'няма'} PTZ методи")
        
        # Проверяваме връзката с устройството
        try:
            # Получаваме информация за устройството
            if hasattr(imou_device, "get_device_info"):
                device_info = await imou_device.get_device_info()
                logger.info(f"Информация за устройството: {device_info}")
                connected = True
            elif hasattr(imou_device, "get_name"):
                device_name = await imou_device.get_name()
                logger.info(f"Име на устройството: {device_name}")
                connected = True
            elif hasattr(imou_device, "is_online"):
                online = await imou_device.is_online()
                logger.info(f"Онлайн: {online}")
                connected = online
            else:
                # Ако не можем да проверим връзката, просто я считаме за успешна
                logger.info("Не можем да проверим връзката директно, продължаваме...")
                connected = True
                
        except Exception as e:
            logger.error(f"Грешка при проверка на връзката: {str(e)}")
            connected = False
        
        if connected:
            logger.info(f"Успешно свързване с Imou устройството")
            update_ptz_config(status="ok")
            return True
        else:
            logger.error("Не може да се установи връзка с устройството")
            update_ptz_config(status="error")
            await api_session.close()
            api_session = None
            return False
            
    except Exception as e:
        logger.error(f"Грешка при свързване с Imou устройство: {str(e)}")
        update_ptz_config(status="error")
        if api_session:
            try:
                await api_session.close()
                api_session = None
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
    config = get_ptz_config()
    
    # Проверяваме дали устройството е инициализирано
    if not imou_device:
        logger.error("Imou устройството не е инициализирано")
        return False
    
    # Проверяваме дали позицията съществува
    if position_id not in config.positions and position_id != 0:
        logger.error(f"Невалидна позиция: {position_id}")
        return False
    
    try:
        # Конвертираме нашата позиция към Imou пресет (1-5 вместо 0-4)
        preset_id = position_id + 1
        
        logger.info(f"Преместване към preset {preset_id} (позиция {position_id}: {config.positions.get(position_id, {}).get('name', f'Позиция {position_id}')})")
        
        # Използваме go_to_preset метода, който е наличен в 1.0.14+
        if hasattr(imou_device, "go_to_preset"):
            await imou_device.go_to_preset(preset_id)
            logger.info(f"Успешно преместване към preset {preset_id}")
            success = True
        # Алтернативно, ако имаме ptz_preset метод
        elif hasattr(imou_device, "ptz_preset"):
            await imou_device.ptz_preset(preset_id)
            logger.info(f"Успешно преместване към preset {preset_id} чрез ptz_preset")
            success = True
        # Ако имаме ptz_control метод
        elif hasattr(imou_device, "ptz_control"):
            # Някои imouapi версии използват ptz_control с команда preset
            await imou_device.ptz_control("preset", {"index": preset_id})
            logger.info(f"Успешно преместване към preset {preset_id} чрез ptz_control")
            success = True
        else:
            logger.error("Не е намерен метод за преместване към preset")
            return False
        
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
    if not imou_device:
        logger.error("Imou устройството не е инициализирано")
        return False
    
    try:
        # Използваме stop_ptz_movement метода, ако е наличен
        if hasattr(imou_device, "stop_ptz_movement"):
            await imou_device.stop_ptz_movement()
            logger.info("Камерата е спряна чрез stop_ptz_movement")
            return True
        # Алтернативно, ако имаме ptz_stop метод
        elif hasattr(imou_device, "ptz_stop"):
            await imou_device.ptz_stop()
            logger.info("Камерата е спряна чрез ptz_stop")
            return True
        # Ако имаме ptz_control метод
        elif hasattr(imou_device, "ptz_control"):
            # Някои imouapi версии използват ptz_control с команда stop
            await imou_device.ptz_control("stop")
            logger.info("Камерата е спряна чрез ptz_control")
            return True
        else:
            # Ако няма метод за спиране, опитваме да преместим към текущата позиция
            config = get_ptz_config()
            current_position = config.current_position
            logger.info(f"Спиране чрез преместване към текущата позиция: {current_position}")
            return await async_move_to_position(current_position)
            
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
    config = get_ptz_config()
    
    if not imou_device:
        logger.error("Imou устройството не е инициализирано")
        return {"error": "Imou устройството не е инициализирано"}
    
    try:
        # В повечето imouapi версии няма директно получаване на текуща позиция
        # връщаме информация базирана на последното известно преместване
        position_id = config.current_position
        position_name = config.positions.get(position_id, {}).get('name', f'Позиция {position_id}')
        
        return {
            "position_id": position_id,
            "position_name": position_name,
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