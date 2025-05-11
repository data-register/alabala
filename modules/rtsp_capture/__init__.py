"""
RTSP Capture модул за ObzorWeather System
"""

from fastapi import APIRouter
from .api import router

# Експортираме router за регистрация в главното приложение
__all__ = ["router"]