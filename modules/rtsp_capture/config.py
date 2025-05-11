"""
Конфигурация на RTSP Capture модул
"""

import os
from pydantic import BaseModel
from datetime import datetime

class RTSPCaptureConfig(BaseModel):
    """Конфигурационен модел за RTSP захващане"""
    rtsp_url: str
    save_dir: str
    interval: int
    width: int
    height: int
    quality: int
    last_frame_path: str = None
    last_frame_time: datetime = None
    status: str = "initializing"
    running: bool = True

# Глобална конфигурация на модула
_config = RTSPCaptureConfig(
    rtsp_url=os.getenv("RTSP_URL", "rtsp://admin:rosenzaq123@87.120.12.193:50911/ch01/0"),
    save_dir=os.getenv("SAVE_DIR", "frames"),
    interval=int(os.getenv("INTERVAL", "60")),
    width=int(os.getenv("WIDTH", "640")),
    height=int(os.getenv("HEIGHT", "480")),
    quality=int(os.getenv("QUALITY", "85"))
)

def get_capture_config() -> RTSPCaptureConfig:
    """Връща текущата конфигурация на модула"""
    return _config

def update_capture_config(**kwargs) -> RTSPCaptureConfig:
    """Обновява конфигурацията с нови стойности"""
    global _config
    
    # Обновяваме само валидните полета
    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
    
    return _config

# Създаваме директорията за запазване на кадри
os.makedirs(_config.save_dir, exist_ok=True)