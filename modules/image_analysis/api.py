"""
API маршрути за Image Analysis модул
"""

import os
import time
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List

from .config import get_analysis_config, update_analysis_config, get_analysis_history
from .analyzer import analyze_image_now, start_analysis_thread, stop_analysis_thread
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("image_analysis_api")

# Регистриране на API router
router = APIRouter()

# Настройване на шаблони
templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def analysis_index(request: Request):
    """Страница за Image Analysis модула"""
    config = get_analysis_config()
    history = get_analysis_history(5)  # Последните 5 анализа
    
    return templates.TemplateResponse("analysis_index.html", {
        "request": request,
        "config": config,
        "history": history,
        "timestamp": int(time.time()),
        "last_update": config.last_analysis_time.strftime("%H:%M:%S") if config.last_analysis_time else "Няма",
        "status": config.status,
        "status_text": "OK" if config.status == "ok" else "Грешка" if config.status == "error" else "Инициализация",
        "has_api_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "image_display_url": "/latest.jpg"
    })

@router.get("/latest")
async def latest_analysis():
    """Връща последния резултат от анализа"""
    config = get_analysis_config()
    
    if not config.last_result:
        return JSONResponse({
            "status": "no_analysis",
            "message": "Все още няма извършен анализ"
        }, status_code=404)
    
    # Форматиране на отговора с по-четима структура
    return JSONResponse({
        "status": config.status,
        "timestamp": config.last_result.timestamp.isoformat() if config.last_result.timestamp else None,
        "cloud_coverage": config.last_result.cloud_coverage,
        "cloud_type": config.last_result.cloud_type,
        "weather_conditions": config.last_result.weather_conditions,
        "confidence": config.last_result.confidence,
        "analysis_time": config.last_result.analysis_time
    })

@router.get("/history")
async def analysis_history(limit: Optional[int] = 10):
    """Връща историята на анализите"""
    history = get_analysis_history(limit)
    
    if not history:
        return JSONResponse({
            "status": "no_history",
            "message": "Няма налична история на анализите"
        }, status_code=404)
    
    # Форматиране на отговора
    history_list = []
    for item in history:
        history_list.append({
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            "cloud_coverage": item.cloud_coverage,
            "cloud_type": item.cloud_type,
            "weather_conditions": item.weather_conditions,
            "confidence": item.confidence,
            "analysis_time": item.analysis_time
        })
    
    return JSONResponse({
        "status": "ok",
        "count": len(history_list),
        "history": history_list
    })

@router.get("/analyze")
async def api_analyze():
    """Принудително извършване на нов анализ"""
    try:
        result = await analyze_image_now()
        
        return JSONResponse({
            "status": "ok",
            "message": "Анализът е успешно извършен",
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "cloud_coverage": result.cloud_coverage,
            "cloud_type": result.cloud_type,
            "weather_conditions": result.weather_conditions,
            "confidence": result.confidence,
            "analysis_time": result.analysis_time
        })
    except Exception as e:
        logger.error(f"Грешка при анализ на изображението: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Не може да се извърши анализ: {str(e)}"
        }, status_code=500)

@router.post("/config")
async def update_config(
    image_url: str = Form(None),
    analysis_interval: int = Form(None),
    anthropic_model: str = Form(None),
    max_tokens: int = Form(None),
    temperature: float = Form(None)
):
    """Обновява конфигурацията на Image Analysis модула"""
    update_params = {}
    
    if image_url is not None:
        update_params["image_url"] = image_url
    
    if analysis_interval is not None:
        update_params["analysis_interval"] = analysis_interval
    
    if anthropic_model is not None:
        update_params["anthropic_model"] = anthropic_model
    
    if max_tokens is not None:
        update_params["max_tokens"] = max_tokens
    
    if temperature is not None:
        update_params["temperature"] = temperature
    
    # Обновяваме конфигурацията
    updated_config = update_analysis_config(**update_params)
    
    return JSONResponse({
        "status": "ok",
        "message": "Конфигурацията е обновена успешно",
        "config": {
            "image_url": updated_config.image_url,
            "analysis_interval": updated_config.analysis_interval,
            "anthropic_model": updated_config.anthropic_model,
            "max_tokens": updated_config.max_tokens,
            "temperature": updated_config.temperature
        }
    })

@router.get("/start")
async def start_analysis():
    """Стартира процеса за анализ на изображения"""
    success = start_analysis_thread()
    
    if success:
        return JSONResponse({
            "status": "ok",
            "message": "Analysis thread started successfully"
        })
    else:
        return JSONResponse({
            "status": "warning",
            "message": "Analysis thread is already running"
        })

@router.get("/stop")
async def stop_analysis():
    """Спира процеса за анализ на изображения"""
    success = stop_analysis_thread()
    
    if success:
        return JSONResponse({
            "status": "ok",
            "message": "Analysis thread stopping"
        })
    else:
        return JSONResponse({
            "status": "error",
            "message": "Failed to stop analysis thread"
        }, status_code=500)