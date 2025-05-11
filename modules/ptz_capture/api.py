# Файл: modules/ptz_capture/api.py
"""
API маршрути за PTZ Capture модул
"""

import os
import time
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import (
    HTMLResponse, FileResponse, JSONResponse, Response
)
from fastapi.templating import Jinja2Templates
from datetime import time as dt_time  # noqa: F401

from .config import get_capture_config, update_capture_config
from .capture import (
    async_capture_all_positions,
    start_capture_thread, stop_capture_thread
)
# Импортираме get_placeholder_image от rtsp_capture модула
from modules.rtsp_capture.capture import get_placeholder_image
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_capture_api")

# Регистриране на API router
router = APIRouter()

# Настройване на шаблони
templates_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
    "templates"
)
templates = Jinja2Templates(directory=templates_dir)


@router.get("/", response_class=HTMLResponse)
async def ptz_capture_index(request: Request):
    """Страница за PTZ Capture модула"""
    config = get_capture_config()
    
    # Подготвяме данни за изобразяване
    active_start = config.active_time_start.strftime("%H:%M")
    active_end = config.active_time_end.strftime("%H:%M")
    
    last_update = (
        config.last_frame_time.strftime("%H:%M:%S") 
        if config.last_frame_time else "Няма"
    )
    
    last_cycle = (
        config.last_complete_cycle_time.strftime("%H:%M:%S") 
        if config.last_complete_cycle_time else "Няма"
    )
    
    status_text = (
        "OK" if config.status == "ok" 
        else "Грешка" if config.status == "error" 
        else "Инициализация"
    )
    
    return templates.TemplateResponse(
        "ptz_capture_index.html", 
        {
            "request": request,
            "config": config,
            "active_start": active_start,
            "active_end": active_end,
            "positions": config.positions,
            "last_update": last_update,
            "last_cycle": last_cycle,
            "status": config.status,
            "status_text": status_text,
            "timestamp": int(time.time())
        }
    )


@router.get("/latest/{position_id}.jpg")
async def latest_position_jpg(position_id: int):
    """Връща последния запазен JPEG файл за определена позиция"""
    try:
        config = get_capture_config()
        
        # Валидиране на позицията
        if position_id not in config.positions and position_id != 0:
            raise HTTPException(
                status_code=404, 
                detail=f"Невалидна позиция: {position_id}"
            )
        
        # Определяме пътя до последния кадър
        position_dir = os.path.join(
            config.save_dir, f"position_{position_id}"
        )
        latest_path = os.path.join(position_dir, "latest.jpg")
        
        if not os.path.exists(latest_path):
            # Връщаме placeholder изображение
            return Response(
                content=get_placeholder_image(), 
                media_type="image/jpeg"
            )
        
        return FileResponse(latest_path, media_type="image/jpeg")
    except Exception as e:
        logger.error(
            f"Грешка при достъпване на последния кадър "
            f"за позиция {position_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info")
async def ptz_capture_info():
    """Връща информация за последния запазен цикъл"""
    config = get_capture_config()
    
    if config.last_complete_cycle_time is None:
        return JSONResponse({
            "status": "no_cycle",
            "message": "Все още няма завършен цикъл на прихващане"
        }, status_code=404)
    
    # Подготвяме информация за всяка позиция
    positions_info = {}
    for pos in config.positions + [0]:
        position_dir = os.path.join(config.save_dir, f"position_{pos}")
        latest_path = os.path.join(position_dir, "latest.jpg")
        
        positions_info[str(pos)] = {
            "latest_path": (
                latest_path if os.path.exists(latest_path) else None
            ),
            "latest_url": f"/ptz/capture/latest/{pos}.jpg",
            "exists": os.path.exists(latest_path)
        }
    
    last_frame_time = (
        config.last_frame_time.isoformat() 
        if config.last_frame_time else None
    )
    
    last_complete_cycle_time = (
        config.last_complete_cycle_time.isoformat() 
        if config.last_complete_cycle_time else None
    )
    
    return JSONResponse({
        "status": config.status,
        "last_frame_time": last_frame_time,
        "last_complete_cycle_time": last_complete_cycle_time,
        "interval": config.interval,
        "positions": positions_info,
        "active_time": {
            "start": config.active_time_start.strftime("%H:%M"),
            "end": config.active_time_end.strftime("%H:%M"),
            "timezone_offset": config.timezone_offset,
            "dst_enabled": config.dst_enabled
        }
    })


@router.get("/capture")
async def api_capture():
    """Принудително извършване на цикъл на прихващане"""
    try:
        # Използваме асинхронната версия директно
        results = await async_capture_all_positions()
        
        config = get_capture_config()
        last_cycle_time = (
            config.last_complete_cycle_time.isoformat() 
            if config.last_complete_cycle_time else None
        )
        
        if all(results.values()):
            return JSONResponse({
                "status": "ok",
                "message": "Цикълът на прихващане е успешно извършен",
                "last_cycle_time": last_cycle_time
            })
        else:
            # Някои позиции са се провалили
            return JSONResponse({
                "status": "partial",
                "message": "Частичен успех при прихващане",
                "results": results,
                "last_cycle_time": last_cycle_time
            })
            
    except Exception as e:
        logger.error(
            f"Грешка при извършване на цикъл на прихващане: {str(e)}"
        )
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)


@router.post("/config")
async def update_config(
    interval: int = Form(None),
    position_wait_time: int = Form(None),
    active_time_start: str = Form(None),
    active_time_end: str = Form(None),
    timezone_offset: int = Form(None),
    dst_enabled: bool = Form(None),
    # Списък с позиции като разделен с запетаи стринг
    positions: str = Form(None)  
):
    """Обновява конфигурацията на PTZ Capture модула"""
    update_params = {}
    
    if interval is not None:
        update_params["interval"] = interval
    
    if position_wait_time is not None:
        update_params["position_wait_time"] = position_wait_time
    
    if active_time_start is not None:
        try:
            hour, minute = map(int, active_time_start.split(':'))
            update_params["active_time_start"] = dt_time(hour, minute)
        except Exception:
            return JSONResponse({
                "status": "error",
                "message": "Невалиден формат за начало на активен период"
            }, status_code=400)
    
    if active_time_end is not None:
        try:
            hour, minute = map(int, active_time_end.split(':'))
            update_params["active_time_end"] = dt_time(hour, minute)
        except Exception:
            return JSONResponse({
                "status": "error",
                "message": "Невалиден формат за край на активен период"
            }, status_code=400)
    
    if timezone_offset is not None:
        update_params["timezone_offset"] = timezone_offset
    
    if dst_enabled is not None:
        update_params["dst_enabled"] = dst_enabled
    
    if positions is not None:
        try:
            pos_list = [
                int(p.strip()) for p in positions.split(',') 
                if p.strip()
            ]
            # Валидираме позициите - трябва да са между 1 и 4
            if all(1 <= p <= 4 for p in pos_list):
                update_params["positions"] = pos_list
            else:
                return JSONResponse({
                    "status": "error",
                    "message": "Невалидни позиции - трябва да са между 1 и 4"
                }, status_code=400)
        except Exception:
            return JSONResponse({
                "status": "error",
                "message": "Невалиден формат за позиции"
            }, status_code=400)
    
    # Обновяваме конфигурацията
    updated_config = update_capture_config(**update_params)
    
    # Форматираме отговора
    response_config = {
        "interval": updated_config.interval,
        "position_wait_time": updated_config.position_wait_time,
        "active_time_start": (
            updated_config.active_time_start.strftime("%H:%M")
        ),
        "active_time_end": updated_config.active_time_end.strftime("%H:%M"),
        "timezone_offset": updated_config.timezone_offset,
        "dst_enabled": updated_config.dst_enabled,
        "positions": updated_config.positions
    }
    
    return JSONResponse({
        "status": "ok",
        "message": "Конфигурацията е обновена успешно",
        "config": response_config
    })


@router.get("/start")
async def start_capture():
    """Стартира процеса за прихващане на кадри"""
    success = start_capture_thread()
    
    if success:
        return JSONResponse({
            "status": "ok",
            "message": "PTZ Capture thread started successfully"
        })
    else:
        return JSONResponse({
            "status": "warning",
            "message": "PTZ Capture thread is already running"
        })


@router.get("/stop")
async def stop_capture():
    """Спира процеса за прихващане на кадри"""
    success = stop_capture_thread()
    
    if success:
        return JSONResponse({
            "status": "ok",
            "message": "PTZ Capture thread stopping"
        })
    else:
        return JSONResponse({
            "status": "error",
            "message": "Failed to stop PTZ capture thread"
        }, status_code=500)