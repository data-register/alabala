# Файл: modules/multi_image_analysis/config.py
"""
Конфигурация на Multi Image Analysis модул
"""

import os
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any

class PositionAnalysisResult(BaseModel):
    """Модел за резултата от анализа на една позиция"""
    position_id: int
    timestamp: Optional[datetime] = None
    cloud_coverage: float = 0.0  # Процент облачност (0-100)
    cloud_type: str = ""  # Тип облаци
    weather_conditions: str = ""  # Описание на метеорологичните условия
    confidence: float = 0.0  # Увереност в анализа (0-100)
    analysis_time: float = 0.0  # Време за анализ в секунди
    full_analysis: Optional[str] = None  # Пълен анализ
    raw_response: Optional[Dict[str, Any]] = None  # Оригинален отговор от API

class MultiAnalysisResult(BaseModel):
    """Модел за обобщения резултат от анализа на всички позиции"""
    timestamp: datetime
    position_results: Dict[int, PositionAnalysisResult] = {}  # Резултати по позиции
    avg_cloud_coverage: float = 0.0  # Среден процент облачност
    overall_weather_conditions: str = ""  # Общо описание на метеорологичните условия
    sunny: bool = False  # Има ли слънце
    total_analysis_time: float = 0.0  # Общо време за анализ

class MultiImageAnalysisConfig(BaseModel):
    """Конфигурационен модел за анализ на множество изображения"""
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_model: str = "claude-3-haiku-20240307"  # По-малък модел за по-бързи отговори
    max_tokens: int = 1000
    temperature: float = 0.2
    analysis_interval: int = 300  # Интервал между анализите в секунди (5 минути)
    last_analysis_time: Optional[datetime] = None
    last_result: Optional[MultiAnalysisResult] = None
    analysis_history: List[MultiAnalysisResult] = []
    status: str = "initializing"
    running: bool = True
    max_history_items: int = 20  # Максимален брой запазени анализи

# Определяме правилния път до файловете
def get_image_dir():
    # Проверка дали сме в Docker среда (Hugging Face)
    if os.path.exists("/app"):
        base_path = "/app/ptz_frames"
    else:
        base_path = "ptz_frames"
    
    return os.getenv("PTZ_FRAMES_DIR", base_path)

# Глобална конфигурация на модула
_config = MultiImageAnalysisConfig(
    anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"), 
    analysis_interval=int(os.getenv("MULTI_ANALYSIS_INTERVAL", "300"))
)

def get_analysis_config() -> MultiImageAnalysisConfig:
    """Връща текущата конфигурация на модула"""
    return _config

def update_analysis_config(**kwargs) -> MultiImageAnalysisConfig:
    """Обновява конфигурацията с нови стойности"""
    global _config
    
    # Обновяваме само валидните полета
    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
    
    return _config

def add_analysis_result(result: MultiAnalysisResult):
    """Добавя нов резултат от анализ и поддържа историята"""
    global _config
    
    # Обновяваме последния резултат
    _config.last_result = result
    _config.last_analysis_time = result.timestamp
    
    # Добавяме в историята
    _config.analysis_history.append(result)
    
    # Ограничаваме размера на историята
    if len(_config.analysis_history) > _config.max_history_items:
        _config.analysis_history = _config.analysis_history[-_config.max_history_items:]

def get_analysis_history(limit: int = None) -> List[MultiAnalysisResult]:
    """Връща историята на анализите с ограничение"""
    if limit is None or limit <= 0:
        return _config.analysis_history
    
    return _config.analysis_history[-limit:]