# Файл: modules/ptz_capture/__init__.py
"""
PTZ Capture модул за ObzorWeather System
"""

from fastapi import APIRouter
from .api import router

# Експортираме router за регистрация в главното приложение
__all__ = ["router"]