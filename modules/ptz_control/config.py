# Файл: modules/ptz_control/config.py
"""
Конфигурация на PTZ Control модул
"""

import os
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


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
    
    # Поддръжка на колекции (пресети)
    collections_supported: bool = False
    collections: Dict[str, Dict[str, Any]] = {}  # Списък колекции (пресети)
    last_collection_id: Optional[str] = None  # Последно използвана колекция
    position_to_collection_map: Dict[int, str] = {}  # Мапинг позиция->колекция
    collection_to_position_map: Dict[str, int] = {}  # Мапинг колекция->позиция


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


def update_collection_mappings(collections: Dict[str, Dict[str, Any]]) -> None:
    """
    Актуализира мапингите между позиции и колекции
    
    Args:
        collections: Речник с колекции от API
    """
    global _config
    
    # Актуализираме колекциите в конфигурацията
    _config.collections = collections
    
    # Ако нямаме колекции, няма нужда от мапинг
    if not collections:
        _config.position_to_collection_map = {}
        _config.collection_to_position_map = {}
        return
    
    # Създаваме нови празни мапинги
    position_to_collection = {}
    collection_to_position = {}
    
    # Опитваме първо да съпоставим колекции към позиции според имената
    position_names = {
        0: ["покой", "home", "default", "по подразбиране", "основна", "center", 
            "център"],
        1: ["изток", "east", "дясно", "right"],
        2: ["запад", "west", "ляво", "left"],
        3: ["север", "north", "горе", "up"],
        4: ["юг", "south", "долу", "down"]
    }
    
    # Опитваме да намерим съвпадения по име
    for collection_id, collection_data in collections.items():
        name = collection_data.get("name", "").lower()
        
        # Търсим съвпадение с име на позиция
        for position_id, name_list in position_names.items():
            if any(position_name in name for position_name in name_list):
                position_to_collection[position_id] = collection_id
                collection_to_position[collection_id] = position_id
                break
    
    # Ако не сме успели да съпоставим всички позиции или имаме твърде малко колекции
    # Просто картографираме според индексите
    if len(position_to_collection) < min(len(_config.positions), len(collections)):
        # Сортираме колекциите по ID (или по име ако ID-тата не са числа)
        sorted_collections = sorted(
            collections.items(), 
            key=lambda x: int(x[0]) if x[0].isdigit() else 0
        )
        
        # Създаваме нови празни мапинги
        position_to_collection = {}
        collection_to_position = {}
        
        # Съпоставяме позиция към колекция по ред
        for i, (collection_id, _) in enumerate(sorted_collections):
            position_id = i
            if position_id in _config.positions:
                position_to_collection[position_id] = collection_id
                collection_to_position[collection_id] = position_id
    
    # Обновяваме мапингите в конфигурацията
    _config.position_to_collection_map = position_to_collection
    _config.collection_to_position_map = collection_to_position