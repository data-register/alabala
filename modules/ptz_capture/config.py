# Файл: modules/ptz_capture/config.py
"""
Конфигурация на PTZ Capture модул
"""

import os
from pydantic import BaseModel
from datetime import datetime, time
from typing import Optional, List, Dict, Any

class PTZCaptureConfig(BaseModel):
    """Конфигурационен модел за PTZ capture"""
    save_dir: str = "/app/ptz_frames"
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

# Глобална конфигурация на модула
_config = PTZCaptureConfig(
    save_dir=os.getenv("PTZ_SAVE_DIR", "ptz_frames"),
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
os.makedirs(_config.save_dir, exist_ok=True)
for pos in _config.positions + [0]:  # Включваме и позиция 0 (покой)
    os.makedirs(os.path.join(_config.save_dir, f"position_{pos}"), exist_ok=True)