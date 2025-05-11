# Файл: modules/ptz_simple/config.py
"""
Конфигурация на PTZ Simple модул
"""

import os
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any, List

class PTZSimpleConfig(BaseModel):
    """Конфигурационен модел за опростен PTZ контрол"""
    camera_ip: str
    camera_port: int
    username: str
    password: str
    status: str = "initializing"
    positions: Dict[int, Dict[str, Any]] = {
        0: {"name": "Покой", "description": "Позиция в покой"},
        1: {"name": "Изток", "description": "Гледа на изток"},
        2: {"name": "Запад", "description": "Гледа на запад"},
        3: {"name": "Север", "description": "Гледа на север"},
        4: {"name": "Юг", "description": "Гледа на юг"}
    }
    move_speed: float = 0.5  # Скорост на движение (0.0 - 1.0)
    last_move_time: Optional[datetime] = None
    current_position: int = 0
    preset_tokens: Dict[int, str] = {}  # Мапинг между нашите позиции и ONVIF пресети

# Глобална конфигурация на модула
_config = PTZSimpleConfig(
    camera_ip=os.getenv("PTZ_CAMERA_IP", "109.160.23.42"),
    camera_port=int(os.getenv("PTZ_CAMERA_PORT", "80")),
    username=os.getenv("PTZ_USERNAME", "admin"),
    password=os.getenv("PTZ_PASSWORD", "admin")
)

def get_ptz_config() -> PTZSimpleConfig:
    """Връща текущата конфигурация на модула"""
    return _config

def update_ptz_config(**kwargs) -> PTZSimpleConfig:
    """Обновява конфигурацията с нови стойности"""
    global _config
    
    # Обновяваме само валидните полета
    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
    
    return _config