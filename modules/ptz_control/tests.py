# Файл: modules/ptz_simple/tests.py
"""
Тестове за PTZ Simple модула
"""

import cv2
import time
import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List

from .config import get_ptz_config
from .controller import (
    initialize_camera_sync,
    get_presets,
    move_to_position,
    stop_movement,
    update_preset_tokens
)
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_simple_tests")

async def test_rtsp_connection(rtsp_url: str) -> Dict[str, Any]:
    """
    Тест за връзка с RTSP потока на камерата
    
    Args:
        rtsp_url: RTSP URL за тестване
        
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    logger.info(f"Тестване на RTSP връзка към: {rtsp_url}")
    start_time = time.time()
    results = {
        "success": False,
        "frame_captured": False,
        "connection_time": 0,
        "error": None,
        "resolution": None
    }
    
    try:
        # Опит за отваряне на RTSP потока
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        connection_time = time.time() - start_time
        results["connection_time"] = connection_time
        
        if not cap.isOpened():
            results["error"] = "Не може да се отвори RTSP потока"
            return results
        
        # Проверка дали можем да прочетем кадър
        ret, frame = cap.read()
        if not ret or frame is None:
            results["error"] = "Не може да се прочете кадър от потока"
            cap.release()
            return results
        
        # Получаваме информация за кадъра
        height, width, channels = frame.shape
        results["resolution"] = f"{width}x{height}"
        results["frame_captured"] = True
        
        # Запазване на тестов кадър
        test_dir = "test_frames"
        os.makedirs(test_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_frame_path = os.path.join(test_dir, f"rtsp_test_{timestamp}.jpg")
        cv2.imwrite(test_frame_path, frame)
        
        # Освобождаване на ресурсите
        cap.release()
        results["success"] = True
        
        logger.info(f"RTSP тест успешен: разделителна способност {results['resolution']}")
        return results
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"RTSP тест неуспешен: {str(e)}")
        return results

def run_rtsp_test(rtsp_url: str) -> Dict[str, Any]:
    """
    Изпълнява тест за RTSP връзка (синхронен метод)
    
    Args:
        rtsp_url: RTSP URL за тестване
        
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_rtsp_connection(rtsp_url))
    finally:
        loop.close()

async def test_preset_movements() -> Dict[str, Any]:
    """
    Тест за преместване между всички пресети и измерване на времето
    
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    logger.info("Тестване на преместване между всички пресети")
    results = {
        "success": False,
        "positions_tested": 0,
        "movement_times": {},
        "avg_movement_time": 0,
        "error": None
    }
    
    try:
        # Инициализиране на камерата
        if not initialize_camera_sync():
            results["error"] = "Неуспешна инициализация на камерата"
            return results
        
        # Обновяваме мапинга между позиции и пресети
        update_preset_tokens()
        
        # Вземаме конфигурацията
        config = get_ptz_config()
        
        # Тестваме само позициите, за които имаме пресет токени
        positions_to_test = [pos_id for pos_id in config.positions.keys() if pos_id in config.preset_tokens]
        results["positions_tested"] = len(positions_to_test)
        
        if not positions_to_test:
            results["error"] = "Няма позиции с намерени пресети за тестване"
            return results
        
        total_time = 0
        
        # Тестване на преместване към всяка позиция
        for position_id in positions_to_test:
            position_name = config.positions[position_id].get("name", f"Позиция {position_id}")
            preset_token = config.preset_tokens[position_id]
            
            logger.info(f"Тестване на преместване към позиция {position_id} ({position_name}), пресет токен: {preset_token}")
            
            start_time = time.time()
            
            # Преместване към позицията
            success = move_to_position(position_id)
            
            if not success:
                logger.error(f"Неуспешно преместване към позиция {position_id}")
                results["movement_times"][position_id] = {
                    "name": position_name,
                    "success": False,
                    "time": 0
                }
                continue
            
            # Изчакване за стабилизиране на позицията
            await asyncio.sleep(2)
            
            movement_time = time.time() - start_time
            total_time += movement_time
            
            # Запазване на времето за преместване
            results["movement_times"][position_id] = {
                "name": position_name,
                "success": True,
                "time": movement_time
            }
            
            logger.info(f"Преместване към позиция {position_id} отне {movement_time:.2f} секунди")
            
            # Добавяме малко изчакване между позициите
            await asyncio.sleep(1)
        
        # Изчисляване на средното време
        if positions_to_test:
            results["avg_movement_time"] = total_time / len(positions_to_test)
        
        results["success"] = True
        
        # Връщаме към начална позиция (0)
        if 0 in positions_to_test:
            move_to_position(0)
        
        logger.info(f"Тест за преместване приключи успешно. Средно време: {results['avg_movement_time']:.2f} секунди")
        return results
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Грешка при тест за преместване: {str(e)}")
        return results

def run_preset_movements_test() -> Dict[str, Any]:
    """
    Изпълнява тест за преместване между всички пресети (синхронен метод)
    
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_preset_movements())
    finally:
        loop.close()

async def test_preset_capture() -> Dict[str, Any]:
    """
    Тест за заснемане на изображения от всички позиции
    
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    logger.info("Тестване на заснемане на изображения от всички позиции")
    results = {
        "success": False,
        "positions_tested": 0,
        "captured_frames": {},
        "total_time": 0,
        "error": None
    }
    
    try:
        # Инициализиране на камерата
        if not initialize_camera_sync():
            results["error"] = "Неуспешна инициализация на камерата"
            return results
        
        # Обновяваме мапинга между позиции и пресети
        update_preset_tokens()
        
        # Вземаме конфигурацията
        config = get_ptz_config()
        
        # Тестваме само позициите, за които имаме пресет токени
        positions_to_test = [pos_id for pos_id in config.positions.keys() if pos_id in config.preset_tokens]
        results["positions_tested"] = len(positions_to_test)
        
        if not positions_to_test:
            results["error"] = "Няма позиции с намерени пресети за тестване"
            return results
        
        # Дефинираме RTSP URL
        rtsp_url = "rtsp://109.160.23.42:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif"
        
        start_total_time = time.time()
        
        # Директория за тестови кадри
        test_dir = "test_frames"
        os.makedirs(test_dir, exist_ok=True)
        
        # Тестване на заснемане от всяка позиция
        for position_id in positions_to_test:
            position_name = config.positions[position_id].get("name", f"Позиция {position_id}")
            
            logger.info(f"Тестване на заснемане от позиция {position_id} ({position_name})")
            
            # Преместване към позицията
            success = move_to_position(position_id)
            
            if not success:
                logger.error(f"Неуспешно преместване към позиция {position_id}")
                results["captured_frames"][position_id] = {
                    "name": position_name,
                    "success": False,
                    "resolution": None,
                    "file_path": None
                }
                continue
            
            # Изчакване за стабилизиране на позицията
            await asyncio.sleep(3)
            
            # Заснемане на кадър
            try:
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                
                if not cap.isOpened():
                    logger.error(f"Не може да се отвори RTSP потока за позиция {position_id}")
                    results["captured_frames"][position_id] = {
                        "name": position_name,
                        "success": False,
                        "resolution": None,
                        "file_path": None
                    }
                    continue
                
                # Прочитане на кадър
                ret, frame = cap.read()
                cap.release()
                
                if not ret or frame is None:
                    logger.error(f"Не може да се прочете кадър за позиция {position_id}")
                    results["captured_frames"][position_id] = {
                        "name": position_name,
                        "success": False,
                        "resolution": None,
                        "file_path": None
                    }
                    continue
                
                # Получаваме информация за кадъра
                height, width, channels = frame.shape
                resolution = f"{width}x{height}"
                
                # Запазване на кадъра
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = os.path.join(test_dir, f"position_{position_id}_{timestamp}.jpg")
                cv2.imwrite(file_path, frame)
                
                # Записване на резултата
                results["captured_frames"][position_id] = {
                    "name": position_name,
                    "success": True,
                    "resolution": resolution,
                    "file_path": file_path
                }
                
                logger.info(f"Успешно заснемане от позиция {position_id}, разделителна способност: {resolution}")
                
            except Exception as e:
                logger.error(f"Грешка при заснемане от позиция {position_id}: {str(e)}")
                results["captured_frames"][position_id] = {
                    "name": position_name,
                    "success": False,
                    "resolution": None,
                    "file_path": None,
                    "error": str(e)
                }
            
            # Добавяме малко изчакване между позициите
            await asyncio.sleep(1)
        
        # Изчисляване на общото време
        results["total_time"] = time.time() - start_total_time
        
        # Връщаме към начална позиция (0)
        if 0 in positions_to_test:
            move_to_position(0)
        
        # Проверка на успеха
        successful_captures = sum(1 for data in results["captured_frames"].values() if data["success"])
        results["success"] = successful_captures > 0
        
        logger.info(f"Тест за заснемане приключи. Успешни заснемания: {successful_captures}/{len(positions_to_test)}")
        return results
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Грешка при тест за заснемане: {str(e)}")
        return results

def run_preset_capture_test() -> Dict[str, Any]:
    """
    Изпълнява тест за заснемане на изображения от всички позиции (синхронен метод)
    
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_preset_capture())
    finally:
        loop.close()

def run_all_tests() -> Dict[str, Any]:
    """
    Изпълнява всички тестове
    
    Returns:
        Dict[str, Any]: Резултати от всички тестове
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "rtsp_test": None,
        "preset_movements_test": None,
        "preset_capture_test": None
    }
    
    # Тест за RTSP връзка
    logger.info("Стартиране на тест за RTSP връзка")
    rtsp_url = "rtsp://109.160.23.42:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif"
    results["rtsp_test"] = run_rtsp_test(rtsp_url)
    
    # Тест за преместване между пресети
    logger.info("Стартиране на тест за преместване между пресети")
    results["preset_movements_test"] = run_preset_movements_test()
    
    # Тест за заснемане от всички позиции
    logger.info("Стартиране на тест за заснемане от всички позиции")
    results["preset_capture_test"] = run_preset_capture_test()
    
    return results