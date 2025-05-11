# Файл: modules/ptz_control/api.py
"""
API маршрути за PTZ Control модул
"""

import os
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from .config import get_ptz_config, update_ptz_config
from .controller import move_to_position, stop_movement, get_current_position, initialize_camera
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_api")

# Регистриране на API router
router = APIRouter()

# Настройване на шаблони
templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def ptz_index(request: Request):
    """Страница за PTZ контрол модула"""
    config = get_ptz_config()
    
    return templates.TemplateResponse("ptz_index.html", {
        "request": request,
        "config": config,
        "current_position": config.current_position,
        "positions": config.positions,
        "status": config.status,
        "status_text": "OK" if config.status == "ok" else "Грешка" if config.status == "error" else "Инициализация"
    })

@router.get("/info")
async def ptz_info():
    """Връща информация за текущото състояние на PTZ камерата"""
    config = get_ptz_config()
    
    return JSONResponse({
        "status": config.status,
        "current_position": get_current_position(),
        "camera_ip": config.camera_ip,
        "camera_port": config.camera_port
    })

@router.get("/position/{position_id}")
async def set_position(position_id: int):
    """Премества камерата към определена позиция"""
    try:
        position_id = int(position_id)
        
        if position_id not in get_ptz_config().positions:
            return JSONResponse({
                "status": "error",
                "message": f"Невалидна позиция: {position_id}"
            }, status_code=400)
        
        success = move_to_position(position_id)
        
        if success:
            return JSONResponse({
                "status": "ok",
                "message": f"Камерата успешно преместена към позиция {position_id}",
                "current_position": get_current_position()
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "Грешка при преместване на камерата"
            }, status_code=500)
    
    except Exception as e:
        logger.error(f"Грешка при задаване на позиция: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)

@router.get("/stop")
async def stop():
    """Спира текущото движение на камерата"""
    try:
        success = stop_movement()
        
        if success:
            return JSONResponse({
                "status": "ok",
                "message": "Камерата е спряна успешно"
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "Грешка при спиране на камерата"
            }, status_code=500)
    
    except Exception as e:
        logger.error(f"Грешка при спиране на камерата: {str(e)}")
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
    """Обновява конфигурацията на PTZ модула"""
    update_params = {}
    
    if camera_ip is not None:
        update_params["camera_ip"] = camera_ip
    
    if camera_port is not None:
        update_params["camera_port"] = camera_port
    
    if username is not None:
        update_params["username"] = username
    
    if password is not None:
        update_params["password"] = password
    
    if move_speed is not None:
        update_params["move_speed"] = move_speed
    
    # Обновяваме конфигурацията
    updated_config = update_ptz_config(**update_params)
    
    # Ако има промени в параметрите за връзка, опитваме се да преинициализираме
    if any(param in update_params for param in ["camera_ip", "camera_port", "username", "password"]):
        initialize_camera()
    
    return JSONResponse({
        "status": "ok",
        "message": "Конфигурацията е обновена успешно",
        "config": {
            "camera_ip": updated_config.camera_ip,
            "camera_port": updated_config.camera_port,
            "username": updated_config.username,
            "password": "********",  # Не връщаме истинската парола
            "move_speed": updated_config.move_speed
        }
    })