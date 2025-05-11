# Файл: modules/ptz_simple/api.py
"""
API маршрути за PTZ Simple модул
"""

import os
import traceback
from fastapi import APIRouter, HTTPException, Query, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, List, Optional

from .config import get_ptz_config, update_ptz_config
from .controller import (
    move_to_position, 
    get_presets, 
    update_preset_tokens, 
    get_current_position, 
    stop_movement,
    run_diagnostics
)
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_simple_api")

# Регистриране на API router
router = APIRouter()

# Настройване на шаблони
templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def ptz_index(request: Request):
    """Страница за PTZ Simple модула"""
    config = get_ptz_config()
    presets = get_presets()
    
    return templates.TemplateResponse("ptz_simple_index.html", {
        "request": request,
        "config": config,
        "presets": presets,
        "current_position": config.current_position,
        "status": config.status,
        "status_text": "OK" if config.status == "ok" else "Грешка" if config.status == "error" else "Инициализация"
    })

@router.get("/positions")
async def get_available_positions():
    """Връща списък с наличните позиции"""
    try:
        config = get_ptz_config()
        positions = []
        
        for position_id, data in config.positions.items():
            positions.append({
                "id": position_id,
                "name": data.get("name", f"Позиция {position_id}"),
                "description": data.get("description", ""),
                "preset_token": config.preset_tokens.get(position_id)
            })
            
        return JSONResponse({
            "status": "ok",
            "message": "Конфигурацията е обновена успешно",
            "config": {
                "camera_ip": updated_config.camera_ip,
                "camera_port": updated_config.camera_port,
                "username": updated_config.username,
                "move_speed": updated_config.move_speed
            }
        })
": "ok",
            "positions": positions,
            "current_position": config.current_position
        })
    
    except Exception as e:
        logger.error(f"Грешка при получаване на позиции: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.get("/position/{position_id}")
async def move_camera_to_position(position_id: int):
    """Премества камерата към определена позиция"""
    try:
        position_id = int(position_id)
        logger.info(f"API заявка за преместване към позиция {position_id}")
        
        config = get_ptz_config()
        if position_id not in config.positions:
            return JSONResponse({
                "status": "error",
                "message": f"Невалидна позиция: {position_id}"
            }, status_code=400)
        
        # Преместваме камерата
        success = move_to_position(position_id)
        
        if success:
            position_name = config.positions[position_id].get("name", f"Позиция {position_id}")
            return JSONResponse({
                "status": "ok",
                "message": f"Камерата успешно преместена към позиция {position_id} ({position_name})",
                "position_id": position_id,
                "position_name": position_name
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": f"Не може да се премести камерата към позиция {position_id}"
            }, status_code=500)
    
    except Exception as e:
        logger.error(f"Грешка при преместване към позиция: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.get("/presets")
async def get_available_presets():
    """Връща списък с наличните пресети от камерата"""
    try:
        presets = get_presets()
        
        # Обновяваме мапинга между позиции и пресети
        update_preset_tokens()
        config = get_ptz_config()
        
        # Форматиране на отговора
        preset_list = []
        for preset_token, preset_data in presets.items():
            # Проверяваме дали този пресет е свързан с някоя позиция
            position_id = None
            for pos_id, token in config.preset_tokens.items():
                if token == preset_token:
                    position_id = pos_id
                    break
            
            preset_list.append({
                "token": preset_token,
                "name": preset_data.get("name", f"Preset {preset_token}"),
                "position_id": position_id,
                "position_name": config.positions.get(position_id, {}).get("name", None) if position_id is not None else None
            })
        
        return JSONResponse({
            "status": "ok",
            "presets": preset_list,
            "preset_tokens": config.preset_tokens,
            "message": f"Намерени {len(presets)} пресета"
        })
    
    except Exception as e:
        logger.error(f"Грешка при получаване на пресети: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.get("/status")
async def get_ptz_status():
    """Връща текущия статус на PTZ контрола"""
    try:
        config = get_ptz_config()
        position_info = get_current_position()
        
        return JSONResponse({
            "status": "ok",
            "ptz_status": config.status,
            "current_position": position_info,
            "preset_tokens": config.preset_tokens,
            "last_move_time": config.last_move_time.isoformat() if config.last_move_time else None
        })
    
    except Exception as e:
        logger.error(f"Грешка при получаване на PTZ статус: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.get("/stop")
async def stop_camera_movement():
    """Спира текущото движение на камерата"""
    try:
        logger.info("API заявка за спиране на движението")
        
        success = stop_movement()
        
        if success:
            return JSONResponse({
                "status": "ok",
                "message": "Движението на камерата е спряно"
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "Не може да се спре движението на камерата"
            }, status_code=500)
    
    except Exception as e:
        logger.error(f"Грешка при спиране на движението: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.get("/diagnostics")
async def api_diagnostics():
    """Извършва диагностика на PTZ функционалността"""
    try:
        logger.info("API заявка за диагностика")
        
        results = run_diagnostics()
        
        return JSONResponse({
            "status": "ok",
            "diagnostics": results
        })
    
    except Exception as e:
        logger.error(f"Грешка при диагностика: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.post("/config")
async def update_config(
    camera_ip: str = Form(None),
    camera_port: int = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    move_speed: float = Form(None)
):
    """Обновява конфигурацията на PTZ Simple модула"""
    update_params = {}
    
    if camera_ip is not None:
        update_params["camera_ip"] = camera_ip
    
    if camera_port is not None:
        update_params["camera_port"] = camera_port
    
    if username is not None:
        update_params["username"] = username
    
    if password is not None and password.strip():
        update_params["password"] = password
    
    if move_speed is not None:
        update_params["move_speed"] = max(0.1, min(1.0, move_speed))
    
    # Обновяваме конфигурацията
    updated_config = update_ptz_config(**update_params)
    
    # Инициализираме камерата с новите настройки, ако са променени IP, порт, потребител или парола
    if any(key in update_params for key in ["camera_ip", "camera_port", "username", "password"]):
        from .controller import initialize
        initialize()
    
    return JSONResponse({
        "status