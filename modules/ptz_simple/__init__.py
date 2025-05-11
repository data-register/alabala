# Файл: modules/ptz_simple/__init__.py
"""
PTZ Simple модул за ObzorWeather System - опростена версия, използваща ONVIF
"""

from fastapi import APIRouter
from .api import router

# Експортираме router за регистрация в главното приложение
__all__ = ["router"]