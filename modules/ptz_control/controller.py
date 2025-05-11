# Файл: modules/ptz_control/controller.py
"""
Контролер за PTZ камерата
"""

import time
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from .config import get_ptz_config, update_ptz_config, update_collection_mappings
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_controller")

# Глобални променливи за комуникация с Imou API
api_client = None
imou_device = None


async def async_initialize_camera() -> bool:
    """
    Асинхронна инициализация на камерата с Imou API
    
    Returns:
        bool: Успешна инициализация или не
    """
    global api_client, imou_device
    config = get_ptz_config()
    
    # Проверяваме дали имаме Imou API данни
    if not (config.app_id and config.app_secret and config.device_serial_number):
        logger.error("Липсват Imou API данни в конфигурацията")
        return False
    
    try:
        # Импортираме imouapi тук, за да избегнем проблеми при импортиране
        try:
            import imouapi
            from imouapi import ImouAPIClient, ImouDevice
            logger.info(f"Намерена imouapi версия: {imouapi.__version__}")
        except ImportError:
            logger.error("imouapi не е инсталирана. Моля инсталирайте с 'pip install imouapi'")
            return False
        
        # Създаваме API клиент за Imou
        try:
            logger.info(f"Инициализиране на Imou API клиент с app_id: {config.app_id}")
            api_client = ImouAPIClient(config.app_id, config.app_secret)
            
            # Проверяваме API връзката
            test_response = await api_client.request("accessToken", {}, useNewVersion=True)
            if test_response and test_response.get("result") == "0":
                logger.info("Успешна API връзка")
            else:
                logger.error(f"Грешка при тестване на API връзка: {test_response}")
                return False
        except Exception as e:
            logger.error(f"Грешка при инициализиране на API клиент: {str(e)}")
            return False
        
        # Създаваме Imou устройство
        try:
            logger.info(f"Инициализиране на устройство {config.device_serial_number}")
            imou_device = ImouDevice(
                api_client, 
                device_id=config.device_serial_number,
                channel=0  # Обикновено камерата е на канал 0
            )
            logger.info("Imou устройство инициализирано успешно")
        except Exception as e:
            logger.error(f"Грешка при инициализиране на устройство: {str(e)}")
            return False
        
        # Обновяваме статуса на конфигурацията
        update_ptz_config(status="ready")
        
        # Получаваме колекциите (пресетите)
        await async_get_collections()
        
        return True
        
    except Exception as e:
        logger.error(f"Грешка при инициализиране на камерата: {str(e)}")
        return False


def initialize_camera() -> bool:
    """
    Инициализира камерата (обвивка около async_initialize_camera)
    
    Returns:
        bool: Успешна инициализация или не
    """
    return asyncio.get_event_loop().run_until_complete(async_initialize_camera())


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
    if position_id not in config.positions:
        logger.error(f"Невалидна позиция: {position_id}")
        return False
    
    logger.info(f"Мапинг позиция->колекция: {config.position_to_collection_map}")
    
    # Проверяваме дали имаме съответстваща колекция за тази позиция
    if config.collections_supported and position_id in config.position_to_collection_map:
        collection_id = config.position_to_collection_map[position_id]
        logger.info(f"Намерена съответстваща колекция {collection_id} за позиция {position_id}")
        return await async_move_to_collection(collection_id)
    
    try:
        # Конвертираме нашата позиция към Imou пресет (1-5 вместо 0-4)
        preset_id = position_id + 1
        position_name = config.positions[position_id].get("name", f"Позиция {position_id}")
        
        logger.info(f"Преместване към preset {preset_id} (позиция {position_id}: {position_name})")
        
        # Използваме go_to_preset метода, който е наличен в 1.0.14+
        success = False
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
            logger.info(f"Използване на метод ptz_control('preset', index={preset_id})")
            await imou_device.ptz_control("preset", {"index": preset_id})
            logger.info(f"Успешно преместване към preset {preset_id} чрез ptz_control")
            success = True
        else:
            # Използваме директен API метод за controlMovePTZ
            logger.info("Използване на директен API метод controlMovePTZ за преместване")
            try:
                params = {
                    "deviceId": config.device_serial_number,
                    "channelId": "0",  # Обикновено е канал 0
                    "operation": str(position_id + 1),  # Операция зависи от позицията
                    "duration": "1000"  # 1 секунда продължителност
                }
                
                logger.info(f"Извикване на controlMovePTZ API с параметри: {params}")
                
                response = await api_client.request(
                    "controlMovePTZ", 
                    params,
                    useNewVersion=True
                )
                
                if response and response.get("result") == "0":
                    logger.info(f"Успешно преместване към позиция {position_id} чрез controlMovePTZ API")
                    success = True
                else:
                    logger.error(f"Грешка при преместване чрез controlMovePTZ: {response}")
                    
                    # Опитваме алтернативен метод - presetControl API
                    logger.info("Опитваме алтернативен метод - presetControl API")
                    preset_params = {
                        "deviceId": config.device_serial_number,
                        "channelId": "0",
                        "type": "1",  # 1 = goto preset
                        "index": str(preset_id)
                    }
                    
                    preset_response = await api_client.request(
                        "presetControl", 
                        preset_params,
                        useNewVersion=True
                    )
                    
                    if preset_response and preset_response.get("result") == "0":
                        logger.info(f"Успешно преместване към позиция {position_id} чрез presetControl API")
                        success = True
                    else:
                        logger.error(f"Грешка при преместване чрез presetControl: {response}")
            except Exception as e:
                logger.error(f"Грешка при директен API метод за преместване: {str(e)}")
                
            if not success:
                logger.error("Не е намерен метод за преместване към preset")
        
        # Обновяваме информацията за текущата позиция
        if success:
            update_ptz_config(
                current_position=position_id,
                last_move_time=datetime.now()
            )
        
        return success
        
    except Exception as e:
        logger.error(f"Грешка при преместване към позиция {position_id}: {str(e)}")
        return False


def move_to_position(position_id: int) -> bool:
    """
    Премества камерата към предварително зададена позиция (обвивка около async функцията)
    
    Args:
        position_id: ID на позицията (0-4)
        
    Returns:
        bool: Успешно преместване или не
    """
    return asyncio.get_event_loop().run_until_complete(async_move_to_position(position_id))


async def async_move_to_collection(collection_id: str) -> bool:
    """
    Асинхронно премества камерата към определена колекция (пресет)
    
    Args:
        collection_id: ID на колекцията от API
        
    Returns:
        bool: Успешно преместване или не
    """
    config = get_ptz_config()
    
    # Проверяваме дали устройството е инициализирано
    if not imou_device or not api_client:
        logger.error("Imou устройството не е инициализирано")
        return False
    
    # Проверяваме дали колекцията съществува
    if collection_id not in config.collections:
        logger.warning(f"Колекция {collection_id} не е намерена, опитваме да обновим")
        
        # Опитваме да опресним колекциите
        collections = await async_get_collections()
        
        # Проверяваме отново
        if not collections or collection_id not in config.collections:
            logger.error(f"Колекция {collection_id} не е намерена дори след обновяване")
            return False
    
    try:
        # Вземаме името на колекцията
        collection_name = config.collections.get(collection_id, {}).get(
            "name", f"Колекция {collection_id}"
        )
        logger.info(f"Преместване към колекция {collection_id} ({collection_name})")
        
        # Използваме API метода за преместване към колекция
        params = {
            "deviceId": config.device_serial_number,
            "channelId": "0",  # Обикновено е канал 0
            "collectionId": collection_id
        }
        
        logger.info(f"Извикване на controlGotoCollection API с параметри: {params}")
        
        response = await api_client.request(
            "controlGotoCollection", 
            params,
            useNewVersion=True
        )
        
        if response and response.get("result") == "0":
            logger.info(f"Успешно преместване към колекция {collection_id}")
            
            # Обновяваме информацията за текущата позиция
            position_id = config.collection_to_position_map.get(collection_id)
            if position_id is not None:
                update_ptz_config(
                    current_position=position_id,
                    last_move_time=datetime.now(),
                    last_collection_id=collection_id
                )
            else:
                # Записваме само последната колекция
                update_ptz_config(
                    last_move_time=datetime.now(),
                    last_collection_id=collection_id
                )
            
            return True
        else:
            logger.error(f"Грешка при преместване към колекция {collection_id}: {response}")
            return False
            
    except Exception as e:
        logger.error(f"Грешка при преместване към колекция {collection_id}: {str(e)}")
        return False


def move_to_collection(collection_id: str) -> bool:
    """
    Премества камерата към определена колекция (обвивка около async функцията)
    
    Args:
        collection_id: ID на колекцията
        
    Returns:
        Dict[str, Dict[str, Any]]: Речник с колекции или празен речник при грешка
    """
    return asyncio.get_event_loop().run_until_complete(async_move_to_collection(collection_id))


async def async_get_collections() -> Dict[str, Dict[str, Any]]:
    """
    Асинхронно получава списъка със запазени колекции (пресети)
    
    Returns:
        Dict[str, Dict[str, Any]]: Речник с колекции или празен речник при грешка
    """
    config = get_ptz_config()
    
    if not api_client:
        logger.error("API клиентът не е инициализиран")
        return {}
    
    try:
        logger.info("Получаване на списъка с колекции (пресети)...")
        
        # Подготовка на параметрите
        params = {
            "deviceId": config.device_serial_number,
            "channelId": "0"  # Обикновено е канал 0
        }
        
        # Извикваме API метода
        response = await api_client.request(
            "getCollection", 
            params,
            useNewVersion=True
        )
        
        if response and response.get("result") == "0":
            raw_collections = response.get("data", {}).get("collections", [])
            
            if raw_collections:
                logger.info(f"Успешно получени {len(raw_collections)} колекции (пресети)")
            else:
                logger.warning("Отговорът не съдържа колекции. Проверете API отговора.")
                logger.debug(f"Пълен отговор: {response}")
            
            # Обработваме колекциите в подходящ формат
            collections = {}
            for collection in raw_collections:
                collection_id = collection.get("id")
                if not collection_id:
                    logger.warning(f"Пропускане на колекция без ID: {collection}")
                    continue
                
                collection_data = {
                    "name": collection.get("name", f"Preset {collection_id}"),
                    "id": collection_id,
                    # Запазваме всички други полета от API отговора
                    **{k: v for k, v in collection.items() if k not in ["id", "name"]}
                }
                
                collections[collection_id] = collection_data
            
            # Маркираме, че поддържаме колекции
            update_ptz_config(collections_supported=True)
            
            # Актуализираме мапингите между позиции и колекции
            update_collection_mappings(collections)
            
            logger.info(f"Обработени {len(collections)} колекции")
            logger.info(f"Мапинг позиция->колекция: {config.position_to_collection_map}")
            logger.info(f"Мапинг колекция->позиция: {config.collection_to_position_map}")
            
            return collections
        else:
            logger.error(f"Грешка при получаване на колекции: {response}")
            logger.info("Опитваме алтернативен метод - getPresets API")
            
            # Опитваме да използваме getPresets API метод като алтернатива
            try:
                preset_params = {
                    "deviceId": config.device_serial_number,
                    "channelId": "0"  # Обикновено е канал 0
                }
                
                preset_response = await api_client.request(
                    "getPresets", 
                    preset_params,
                    useNewVersion=True
                )
                
                if preset_response and preset_response.get("result") == "0":
                    presets = preset_response.get("data", {}).get("presets", [])
                    logger.info(f"Успешно получени {len(presets)} пресети")
                    
                    # Създаваме колекции от пресетите
                    collections = {}
                    for i, preset in enumerate(presets):
                        preset_id = str(i + 1)  # Преместваме от 1-базиран индекс
                        name = preset.get("name", f"Preset {preset_id}")
                        
                        collections[preset_id] = {
                            "id": preset_id,
                            "name": name,
                            **{k: v for k, v in preset.items() if k != "name"}
                        }
                    
                    # Актуализираме мапингите между позиции и колекции
                    update_ptz_config(collections_supported=True)
                    update_collection_mappings(collections)
                    
                    return collections
                else:
                    logger.error(f"Грешка при получаване на пресети: {preset_response}")
                    return {}
            except Exception as e:
                logger.error(f"Грешка при получаване на пресети: {str(e)}")
                return {}
            
    except Exception as e:
        logger.error(f"Грешка при получаване на колекции: {str(e)}")
        return {}


def get_collections() -> Dict[str, Dict[str, Any]]:
    """
    Получава списъка със запазени колекции (пресети)
    (обвивка около async функцията)
    
    Returns:
        Dict[str, Dict[str, Any]]: Речник с колекции
    """
    return asyncio.get_event_loop().run_until_complete(async_get_collections())


async def async_stop_movement() -> bool:
    """
    Асинхронно спира движението на камерата
    
    Returns:
        bool: Успешно спиране или не
    """
    config = get_ptz_config()
    
    # Проверяваме дали устройството е инициализирано
    if not imou_device or not api_client:
        logger.error("Imou устройството не е инициализирано")
        return False
    
    try:
        # Опитваме първо методите на ImouDevice
        if hasattr(imou_device, "ptz_stop"):
            await imou_device.ptz_stop()
            logger.info("Успешно спиране на движението чрез ptz_stop")
            return True
        elif hasattr(imou_device, "ptz_control") and "stop" in str(imou_device.ptz_control):
            await imou_device.ptz_control("stop")
            logger.info("Успешно спиране на движението чрез ptz_control(stop)")
            return True
        else:
            # Използваме директен API метод
            params = {
                "deviceId": config.device_serial_number,
                "channelId": "0",  # Обикновено е канал 0
                "operation": "10",  # 10 = stop според Imou API
                "duration": "1000"  # 1 секунда продължителност
            }
            
            logger.info(f"Извикване на controlMovePTZ API с параметри: {params}")
            
            response = await api_client.request(
                "controlMovePTZ", 
                params,
                useNewVersion=True
            )
            
            if response and response.get("result") == "0":
                logger.info("Успешно спиране на движението чрез API")
                return True
            else:
                logger.error(f"Грешка при спиране на движението: {response}")
                return False
    
    except Exception as e:
        logger.error(f"Грешка при спиране на движението: {str(e)}")
        return False


def stop_movement() -> bool:
    """
    Спира движението на камерата (обвивка около async функцията)
    
    Returns:
        bool: Успешно спиране или не
    """
    return asyncio.get_event_loop().run_until_complete(async_stop_movement())


def get_current_position() -> Dict[str, Any]:
    """
    Връща информация за текущата позиция
    
    Returns:
        Dict[str, Any]: Информация за текущата позиция
    """
    config = get_ptz_config()
    current_position = config.current_position
    
    result = {
        "position_id": current_position,
        "position_name": config.positions[current_position].get(
            "name", f"Позиция {current_position}"
        ),
        "position_description": config.positions[current_position].get(
            "description", ""
        ),
        "last_move_time": config.last_move_time
    }
    
    # Добавяме информация за колекцията, ако е налична
    collection_id = config.position_to_collection_map.get(current_position)
    
    if config.last_collection_id:
        result["last_collection_id"] = config.last_collection_id
        
        if config.last_collection_id in config.collections:
            result["collection_name"] = config.collections[config.last_collection_id].get(
                "name", f"Колекция {config.last_collection_id}"
            )
    
    if collection_id:
        result["collection_id"] = collection_id
        
        if collection_id in config.collections:
            result["collection_name"] = config.collections[collection_id].get(
                "name", f"Колекция {collection_id}"
            )
    
    return result


def initialize() -> bool:
    """
    Инициализира PTZ контрол модула
    
    Returns:
        bool: Успешна инициализация или не
    """
    success = initialize_camera()
    
    if success:
        logger.info("PTZ контрол модул с Imou API инициализиран успешно")
        
        # Получаване на колекциите (пресетите)
        collections = get_collections()
        if collections:
            config = get_ptz_config()
            logger.info(f"Получени са {len(collections)} колекции (пресети)")
            logger.info(f"Мапинг позиция->колекция: {config.position_to_collection_map}")
            logger.info(f"Мапинг колекция->позиция: {config.collection_to_position_map}")
        else:
            # Ако не сме получили колекции, може би трябва да създадете пресети в приложението
            logger.info("Не са получени колекции (пресети). "
                        "Опитайте да създадете пресети в Imou Life приложението.")
    else:
        logger.error("Грешка при инициализиране на PTZ контрол модул чрез Imou API")
    
    return success