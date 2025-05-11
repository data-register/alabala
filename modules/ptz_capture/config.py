# Файл: modules/ptz_capture/config.py
"""
Конфигурация на PTZ Capture модул
"""

import os
import logging
from pydantic import BaseModel
from datetime import datetime, time
from typing import Optional, List, Dict, Any

class PTZCaptureConfig(BaseModel):
    """Конфигурационен модел за PTZ capture"""
    save_dir: str = "/app/ptz_frames"  # Променено от "ptz_frames" на "/app/ptz_frames" за Docker
    interval: int = 1800  # 30 минути в секунди
    position_wait_time: int = 10  # Време за изчакване след позициониране в секунди
    active_time_start: time = time(6, 0)  # Начало на активния период (6:00)
    active_time_end: time = time(21, 0)  # Край на активния период (21:00)
    timezone_offset: int = 2  # Часова зона (UTC+2)
    dst_enabled: bool = True  # Лятно часово време (+1 час)
    positions: List[int] = [1, 2, 3, 4]  # Позиции за обхождане (без 0 - покой)
    last_frame_paths: Dict[int, str] = {}  # Пътища към последните кадри по позиции
    last_frame_time: Optional[datetime] = None
    last_complete_cycle_time: Optional[datetime] = None
    status: str = "initializing"
    running: bool = True
    
    class Config:
        arbitrary_types_allowed = True

# Проверяваме дали сме в Docker среда и съответно определяме пътя
def get_ptz_frames_dir():
    # Проверка дали сме в Docker среда (Hugging Face)
    if os.path.exists("/app"):
        return "/app/ptz_frames"
    else:
        return os.getenv("PTZ_SAVE_DIR", "ptz_frames")

# Настройване на логер за този модул
logging.basicConfig(level=logging.INFO)
config_logger = logging.getLogger("ptz_capture_config")

# Глобална конфигурация на модула
_config = PTZCaptureConfig(
    save_dir=get_ptz_frames_dir(),
    interval=int(os.getenv("PTZ_INTERVAL", "1800")),
    position_wait_time=int(os.getenv("PTZ_POSITION_WAIT", "10")),
    active_time_start=time(int(os.getenv("PTZ_ACTIVE_START_HOUR", "6")), 0),
    active_time_end=time(int(os.getenv("PTZ_ACTIVE_END_HOUR", "21")), 0),
    timezone_offset=int(os.getenv("TIMEZONE_OFFSET", "2")),
    dst_enabled=os.getenv("DST_ENABLED", "True").lower() in ("true", "1", "yes")
)

def get_capture_config() -> PTZCaptureConfig:
    """Връща текущата конфигурация на модула"""
    return _config

def update_capture_config(**kwargs) -> PTZCaptureConfig:
    """Обновява конфигурацията с нови стойности"""
    global _config
    
    # Обновяваме само валидните полета
    for key, value in kwargs.items():
        if hasattr(_config, key):
            # Специална обработка за time полетата
            if key in ["active_time_start", "active_time_end"] and isinstance(value, str):
                try:
                    hour, minute = map(int, value.split(":"))
                    value = time(hour, minute)
                except:
                    continue
            
            setattr(_config, key, value)
    
    return _config

# Създаваме директорията за запазване на кадри
try:
    # Опитваме няколко възможни пътища
    paths_to_try = [
        _config.save_dir,  # Пробваме директно пътя от конфигурацията
        "ptz_frames",      # Пробваме релативен път
        "/app/ptz_frames"  # Пробваме абсолютен път (Docker)
    ]
    
    # Намира първият път, който може да използваме
    success_path = None
    for path in paths_to_try:
        try:
            config_logger.info(f"Опитваме да създадем/проверим директория: {path}")
            os.makedirs(path, exist_ok=True)
            
            # Проверяваме дали директорията е записваема
            test_file = os.path.join(path, "test_write.txt")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            
            success_path = path
            config_logger.info(f"Успешно използваме директория: {path}")
            
            # Ако успешно сме създали директория, но не е същата като в конфигурацията,
            # актуализираме конфигурацията
            if path != _config.save_dir:
                _config.save_dir = path
                config_logger.info(f"Актуализирана директория в конфигурацията: {path}")
                
            break
        except Exception as e:
            config_logger.warning(f"Не може да се използва директория {path}: {str(e)}")
    
    # Ако сме намерили работеща директория, създаваме поддиректориите
    if success_path:
        for pos in _config.positions + [0]:  # Включваме и позиция 0 (покой)
            pos_dir = os.path.join(success_path, f"position_{pos}")
            try:
                os.makedirs(pos_dir, exist_ok=True)
                config_logger.info(f"Създадена поддиректория: {pos_dir}")
            except Exception as e:
                config_logger.error(f"Грешка при създаване на поддиректория {pos_dir}: {str(e)}")
    else:
        config_logger.error("Не е намерена работеща директория за ptz_frames!")
        
except Exception as e:
    config_logger.error(f"Основна грешка при настройка на директории: {str(e)}")