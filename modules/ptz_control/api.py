# Файл: modules/ptz_control/api.py

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional

from .config import get_ptz_config
from .controller import (
    move_to_position, move_to_collection,
    get_collections, get_current_position, stop_movement
)
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_control_api")

router = APIRouter(prefix="/api/ptz", tags=["PTZ Control"])


@router.get("/positions")
async def get_available_positions():
    """Връща списък с наличните позиции"""
    try:
        config = get_ptz_config()
        positions = []
        
        for position_id, data in config.positions.items():
            # Проверяваме дали имаме съответна колекция за тази позиция
            collection_id = config.position_to_collection_map.get(position_id)
            collection_name = None
            if collection_id and collection_id in config.collections:
                collection_name = config.collections[collection_id].get("name")
                
            positions.append({
                "id": position_id,
                "name": data.get("name", f"Позиция {position_id}"),
                "description": data.get("description", ""),
                "collection_id": collection_id,
                "collection_name": collection_name
            })
            
        return JSONResponse({
            "status": "ok",
            "positions": positions,
            "current_position": config.current_position
        })
    
    except Exception as e:
        logger.error(f"Грешка при получаване на позиции: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)


@router.get("/move/{position_id}")
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
        
        # Проверяваме дали имаме колекция за тази позиция
        collection_id = None
        if config.collections_supported and position_id in config.position_to_collection_map:
            collection_id = config.position_to_collection_map[position_id]
            logger.info(f"Позиция {position_id} съответства на колекция {collection_id}")
        
        # Преместваме камерата
        success = await move_to_position(position_id)
        
        if success:
            position_name = config.positions[position_id].get("name", f"Позиция {position_id}")
            message = f"Камерата успешно преместена към позиция {position_id} ({position_name})"
            
            # Добавяме информация за колекцията, ако е използвана
            if collection_id:
                collection_name = config.collections.get(collection_id, {}).get(
                    "name", f"Колекция {collection_id}"
                )
                message += f" чрез колекция {collection_id} ({collection_name})"
                
            return JSONResponse({
                "status": "ok",
                "message": message,
                "position_id": position_id,
                "position_name": position_name,
                "collection_id": collection_id
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": f"Не може да се премести камерата към позиция {position_id}"
            }, status_code=500)
    
    except Exception as e:
        logger.error(f"Грешка при преместване към позиция: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)


@router.get("/collections")
async def get_available_collections():
    """Връща списък с наличните колекции (пресети)"""
    try:
        # Извикваме get_collections, за да обновим списъка с колекции
        await get_collections()
        
        # Вземаме актуалната конфигурация
        config = get_ptz_config()
        
        # Подготвяме информация за UI
        collection_info = []
        for collection_id, data in config.collections.items():
            position_id = config.collection_to_position_map.get(collection_id)
            position_name = None
            if position_id is not None and position_id in config.positions:
                position_name = config.positions[position_id].get("name")
                
            collection_info.append({
                "id": collection_id,
                "name": data.get("name", f"Preset {collection_id}"),
                "position_id": position_id,
                "position_name": position_name
            })
        
        return JSONResponse({
            "status": "ok",
            "message": f"Намерени {len(config.collections)} колекции",
            "collections": collection_info,
            "position_to_collection": config.position_to_collection_map,
            "collection_to_position": config.collection_to_position_map,
            "collections_supported": config.collections_supported
        })
    
    except Exception as e:
        logger.error(f"Грешка при получаване на колекции: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)


@router.get("/collection/{collection_id}")
async def move_camera_to_collection(collection_id: str):
    """Премества камерата към определена колекция (пресет)"""
    try:
        logger.info(f"API заявка за преместване към колекция {collection_id}")
        
        # Преместваме камерата
        success = await move_to_collection(collection_id)
        
        if success:
            config = get_ptz_config()
            collection_name = config.collections.get(collection_id, {}).get(
                "name", f"Колекция {collection_id}"
            )
            
            # Проверяваме дали имаме съответна позиция
            position_id = config.collection_to_position_map.get(collection_id)
            position_info = ""
            if position_id is not None:
                position_name = config.positions.get(position_id, {}).get(
                    "name", f"Позиция {position_id}"
                )
                position_info = f" (съответства на позиция {position_id}: {position_name})"
                
            return JSONResponse({
                "status": "ok",
                "message": f"Камерата успешно преместена към колекция {collection_id} "
                          f"({collection_name}){position_info}",
                "collection_id": collection_id,
                "collection_name": collection_name,
                "position_id": position_id
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": f"Не може да се премести камерата към колекция {collection_id}"
            }, status_code=500)
    
    except Exception as e:
        logger.error(f"Грешка при преместване към колекция: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)


@router.get("/refresh")
async def refresh_collections():
    """Обновява списъка с налични колекции (пресети)"""
    try:
        logger.info("API заявка за обновяване на колекциите")
        
        # Извикваме get_collections за да обновим списъка
        collections = await get_collections()
        
        if collections:
            config = get_ptz_config()
            return JSONResponse({
                "status": "ok",
                "message": f"Успешно обновени {len(collections)} колекции",
                "collections": collections,
                "position_to_collection": config.position_to_collection_map,
                "collection_to_position": config.collection_to_position_map
            })
        else:
            return JSONResponse({
                "status": "warning",
                "message": "Не са намерени колекции или възникна грешка"
            })
    
    except Exception as e:
        logger.error(f"Грешка при обновяване на колекциите: {str(e)}")
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
            "collections_supported": config.collections_supported,
            "collections_count": len(config.collections) if config.collections else 0,
            "last_move_time": config.last_move_time
        })
    
    except Exception as e:
        logger.error(f"Грешка при получаване на PTZ статус: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)


@router.get("/stop")
async def stop_camera_movement():
    """Спира текущото движение на камерата"""
    try:
        logger.info("API заявка за спиране на движението")
        
        success = await stop_movement()
        
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
        return JSONResponse({
            "status": "error",
            "message": f"Грешка: {str(e)}"
        }, status_code=500)