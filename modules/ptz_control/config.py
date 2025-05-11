# Файл: modules/ptz_control/config.py
"""
Конфигурация на PTZ Control модул
"""

import os
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any

class PTZControlConfig(BaseModel):
    """Конфигурационен модел за PTZ контрол"""
    # Imou API конфигурация
    app_id: str
    app_secret: str
    device_serial_number: str
    
    # Запазваме съществуващата конфигурация за съвместимост
    camera_ip: Optional[str] = None
    camera_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    wsdl_path: Optional[str] = None  # Път към WSDL файл, ако е необходим
    
    positions: Dict[int, Dict[str, Any]] = {
        0: {"name": "Покой", "description": "Позиция в покой"},
        1: {"name": "Изток", "description": "Гледа на изток"},
        2: {"name": "Запад", "description": "Гледа на запад"},
        3: {"name": "Север", "description": "Гледа на север"},
        4: {"name": "Юг", "description": "Гледа на юг"}
    }
    move_speed: float = 0.5  # Скорост на движение (0.0 - 1.0)
    status: str = "initializing"
    last_move_time: Optional[datetime] = None
    current_position: int = 0

# Глобална конфигурация на модула
_config = PTZControlConfig(
    # Imou API данни от environment променливи или стойности по подразбиране
    app_id=os.environ.get("IMOU_APP_ID", "lcb51c9bdb8b44452f"),
    app_secret=os.environ.get("IMOU_APP_SECRET", "ea9432614b9a461ab7928f03d14a3f"),
    device_serial_number=os.environ.get("IMOU_DEVICE_SN", "B2762ADPCG9BBD4"),
    
    # Запазваме оригиналните полета за съвместимост
    camera_ip=os.getenv("PTZ_CAMERA_IP", "192.168.1.100"),
    camera_port=int(os.getenv("PTZ_CAMERA_PORT", "8899")),
    username=os.getenv("PTZ_USERNAME", "admin"),
    password=os.getenv("PTZ_PASSWORD", "admin")
)

def get_ptz_config() -> PTZControlConfig:
    """Връща текущата конфигурация на модула"""
    return _config

def update_ptz_config(**kwargs) -> PTZControlConfig:
    """Обновява конфигурацията с нови стойности"""
    global _config
    
    # Обновяваме само валидните полета
    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
    
    return _config