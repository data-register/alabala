# Файл: modules/multi_image_analysis/api.py
"""
API маршрути за Multi Image Analysis модул
"""

import os
import time
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict

from .config import get_analysis_config, update_analysis_config, get_analysis_history
from .analyzer import analyze_images_now, start_analysis_thread, stop_analysis_thread
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("multi_image_analysis_api")

# Регистриране на API router
router = APIRouter()

# Настройване на шаблони
templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def multi_analysis_index(request: Request):
    """Страница за Multi Image Analysis модула"""
    config = get_analysis_config()
    history = get_analysis_history(5)  # Последните 5 анализа
    
    # Подготвяме позициите за показване
    from modules.ptz_capture.config import get_capture_config as get_ptz_config
    ptz_config = get_ptz_config()
    positions = ptz_config.positions
    
    return templates.TemplateResponse("multi_analysis_index.html", {
        "request": request,
        "config": config,
        "history": history,
        "timestamp": int(time.time()),
        "last_update": config.last_analysis_time.strftime("%H:%M:%S") if config.last_analysis_time else "Няма",
        "status": config.status,
        "status_text": "OK" if config.status == "ok" else "Грешка" if config.status == "error" else "Инициализация",
        "has_api_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "positions": positions
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
    
    # Подготвяме резултатите по позиции
    position_results = {}
    for pos_id, result in config.last_result.position_results.items():
        position_results[str(pos_id)] = {
            "cloud_coverage": result.cloud_coverage,
            "cloud_type": result.cloud_type,
            "weather_conditions": result.weather_conditions,
            "confidence": result.confidence,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None
        }
    
    # Форматиране на отговора с по-четима структура
    return JSONResponse({
        "status": config.status,
        "timestamp": config.last_result.timestamp.isoformat() if config.last_result.timestamp else None,
        "avg_cloud_coverage": config.last_result.avg_cloud_coverage,
        "overall_weather_conditions": config.last_result.overall_weather_conditions,
        "sunny": config.last_result.sunny,
        "total_analysis_time": config.last_result.total_analysis_time,
        "position_results": position_results
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
        # Подготвяме резултатите по позиции
        position_results = {}
        for pos_id, result in item.position_results.items():
            position_results[str(pos_id)] = {
                "cloud_coverage": result.cloud_coverage,
                "cloud_type": result.cloud_type,
                "weather_conditions": result.weather_conditions,
                "confidence": result.confidence
            }
        
        history_list.append({
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            "avg_cloud_coverage": item.avg_cloud_coverage,
            "overall_weather_conditions": item.overall_weather_conditions,
            "sunny": item.sunny,
            "total_analysis_time": item.total_analysis_time,
            "position_results": position_results
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
        result = await analyze_images_now()
        
        # Подготвяме резултатите по позиции
        position_results = {}
        for pos_id, pos_result in result.position_results.items():
            position_results[str(pos_id)] = {
                "cloud_coverage": pos_result.cloud_coverage,
                "cloud_type": pos_result.cloud_type,
                "weather_conditions": pos_result.weather_conditions,
                "confidence": pos_result.confidence
            }
        
        return JSONResponse({
            "status": "ok",
            "message": "Анализът е успешно извършен",
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "avg_cloud_coverage": result.avg_cloud_coverage,
            "overall_weather_conditions": result.overall_weather_conditions,
            "sunny": result.sunny,
            "total_analysis_time": result.total_analysis_time,
            "position_results": position_results
        })
    except Exception as e:
        logger.error(f"Грешка при анализ на изображенията: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Не може да се извърши анализ: {str(e)}"
        }, status_code=500)

@router.post("/config")
async def update_config(
    analysis_interval: int = Form(None),
    anthropic_model: str = Form(None),
    max_tokens: int = Form(None),
    temperature: float = Form(None)
):
    """Обновява конфигурацията на Multi Image Analysis модула"""
    update_params = {}
    
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