# Файл: test_ptz.py
"""
Самостоятелен скрипт за тестване на PTZ функционалността
"""

import os
import sys
import time
import json
import logging
import asyncio
import cv2
from datetime import datetime
from typing import Dict, Any, List, Optional

# Конфигурация на логера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("ptz_test.log")
    ]
)
logger = logging.getLogger("ptz_test")

# Настройки на камерата
CAMERA_IP = "109.160.23.42"
CAMERA_PORT = 80
USERNAME = "admin"
PASSWORD = "admin"
RTSP_URL = f"rtsp://{CAMERA_IP}:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif"

# Настройки на теста
TEST_DIR = "test_frames"
os.makedirs(TEST_DIR, exist_ok=True)

# Инициализация на ONVIF камера
try:
    from onvif import ONVIFCamera
    import zeep
    
    # Фиксиране на известен проблем със zeep библиотеката
    def zeep_pythonvalue(self, xmlvalue):
        return xmlvalue
    
    zeep.xsd.simple.AnySimpleType.pythonvalue = zeep_pythonvalue
    
except ImportError:
    logger.error("ONVIF библиотеката не е инсталирана. Инсталирайте я с: pip install onvif-zeep")
    sys.exit(1)

async def test_camera_connection() -> Dict[str, Any]:
    """
    Тест за връзка с ONVIF камерата
    
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    results = {
        "success": False,
        "error": None,
        "profiles_count": 0,
        "profile_token": None
    }
    
    try:
        logger.info(f"Опит за свързване с камера: {CAMERA_IP}:{CAMERA_PORT}")
        start_time = time.time()
        
        # Създаване на ONVIF камера
        cam = ONVIFCamera(CAMERA_IP, CAMERA_PORT, USERNAME, PASSWORD)
        
        # Създаване на медия услуга
        media = cam.create_media_service()
        
        # Получаване на профили
        profiles = media.GetProfiles()
        results["profiles_count"] = len(profiles)
        
        if not profiles:
            results["error"] = "Не са намерени профили"
            return results
        
        # Вземаме първия профил
        results["profile_token"] = profiles[0].token
        
        # Създаване на PTZ услуга
        ptz = cam.create_ptz_service()
        
        # Проверка дали можем да получим статуса
        status = ptz.GetStatus({'ProfileToken': results["profile_token"]})
        
        # Ако получаваме статус, връзката е успешна
        results["success"] = True
        results["connection_time"] = time.time() - start_time
        
        logger.info(f"Успешна връзка с камерата, време: {results['connection_time']:.2f} сек")
        return results
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Грешка при свързване с камерата: {str(e)}")
        return results

async def get_camera_presets() -> Dict[str, Any]:
    """
    Получаване на наличните пресети от камерата
    
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    results = {
        "success": False,
        "error": None,
        "presets": {},
        "presets_count": 0
    }
    
    try:
        logger.info("Получаване на пресети от камерата")
        
        # Създаване на ONVIF камера
        cam = ONVIFCamera(CAMERA_IP, CAMERA_PORT, USERNAME, PASSWORD)
        
        # Създаване на медия услуга
        media = cam.create_media_service()
        
        # Получаване на профили
        profiles = media.GetProfiles()
        
        if not profiles:
            results["error"] = "Не са намерени профили"
            return results
        
        # Вземаме първия профил
        profile_token = profiles[0].token
        
        # Създаване на PTZ услуга
        ptz = cam.create_ptz_service()
        
        # Получаване на пресети
        presets = ptz.GetPresets({'ProfileToken': profile_token})
        
        # Обработваме пресетите
        presets_dict = {}
        for preset in presets:
            # Различните камери могат да имат различна структура на пресетите
            preset_token = preset.get('token') or preset.get('PresetToken')
            preset_name = preset.get('Name', f"Preset {preset_token}")
            
            presets_dict[preset_token] = {
                'name': preset_name,
                'token': preset_token
            }
        
        results["presets"] = presets_dict
        results["presets_count"] = len(presets_dict)
        results["success"] = True
        
        logger.info(f"Получени {results['presets_count']} пресета от камерата")
        return results
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Грешка при получаване на пресети: {str(e)}")
        return results

async def move_to_preset(preset_token: str) -> Dict[str, Any]:
    """
    Преместване на камерата към определен пресет
    
    Args:
        preset_token: Токен на пресета
        
    Returns:
        Dict[str, Any]: Резултати от теста
    """
    results = {
        "success": False,
        "error": None,
        "movement_time": 0
    }
    
    try:
        logger.info(f"Преместване към пресет: {preset_token}")
        start_time = time.time()
        
        # Създаване на ONVIF камера
        cam = ONVIFCamera(CAMERA_IP, CAMERA_PORT, USERNAME, PASSWORD)
        
        # Създаване на медия услуга
        media = cam.create_media_service()
        
        # Получаване на профили
        profiles = media.GetProfiles()
        
        if not profiles:
            results["error"] = "Не са намерени профили"
            return results
        
        # Вземаме първия профил
        profile_token = profiles[0].token
        
        # Създаване на PTZ услуга
        ptz = cam.create_ptz_service()
        
        # Преместване към пресет
        ptz.GotoPreset({
            'ProfileToken': profile_token,
            'PresetToken': preset_token,
            'Speed': {
                'PanTilt': {'x': 0.5, 'y': 0.5},
                'Zoom': {'x': 0.5}
            }
        })
        
        # Изчакване за стабилизация
        await asyncio.sleep(3)
        
        movement_time = time.time() - start_time
        results["movement_time"] = movement_time
        results["success"] = True
        
        logger.info(f"Успешно преместване към пресет {preset_token} за {movement_time:.2f} секунди")
        return results
        
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Грешка при преместване към пресет: {str(e)}")
        return results