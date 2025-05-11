# Файл: app.py

"""
Основно приложение на ObzorWeather система
Този файл инициализира FastAPI приложението и зарежда всички модули.
"""

import os
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Първо създаваме логър преди всичко останало
import logging
logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Създаваме необходимите директории преди да импортираме модулите
required_dirs = [
    "static", 
    "templates", 
    "frames", 
    "logs",
    "ptz_frames"
]

for dir_name in required_dirs:
    try:
        # Опитваме с абсолютен път (за Docker)
        if os.path.exists("/app"):
            full_path = os.path.join("/app", dir_name)
        else:
            full_path = dir_name
            
        os.makedirs(full_path, exist_ok=True)
        logger.info(f"Директория създадена/проверена: {full_path}")
        
        # За ptz_frames създаваме и поддиректории за всяка позиция
        if dir_name == "ptz_frames":
            for pos in range(5):  # Позиции 0-4
                pos_dir = os.path.join(full_path, f"position_{pos}")
                os.makedirs(pos_dir, exist_ok=True)
                logger.info(f"Поддиректория създадена/проверена: {pos_dir}")
                
                # Проверка дали директорията е записваема
                try:
                    test_file = os.path.join(pos_dir, "test_write.txt")
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    logger.info(f"Директорията {pos_dir} е записваема")
                except Exception as e:
                    logger.error(f"Директорията {pos_dir} НЕ Е записваема: {str(e)}")
    except Exception as e:
        logger.error(f"Грешка при създаване на директория {dir_name}: {str(e)}")
        
# След като директориите са създадени, импортираме utils и останалите модули
from utils.logger import setup_logger

# Инициализиране на логване
logger = setup_logger("app")

# Импортиране на модули след създаване на директориите
try:
    # Импортиране на модули
    from modules.rtsp_capture import router as rtsp_router
    from modules.rtsp_capture.config import get_capture_config
    # Добавяме модул за анализ на изображения
    from modules.image_analysis import router as analysis_router
    from modules.image_analysis.config import get_analysis_config

    # Добавяме новите PTZ модули
    from modules.ptz_control import router as ptz_control_router
    from modules.ptz_control.config import get_ptz_config
    from modules.ptz_capture import router as ptz_capture_router
    from modules.ptz_capture.config import get_capture_config as get_ptz_capture_config
    from modules.multi_image_analysis import router as multi_analysis_router
    from modules.multi_image_analysis.config import get_analysis_config as get_multi_analysis_config
except Exception as e:
    logger.error(f"Грешка при импортиране на модули: {str(e)}")
    sys.exit(1)

# Създаваме FastAPI приложение
app = FastAPI(
    title="ObzorWeather System",
    description="Модулна система за метеорологичен мониторинг",
    version="1.0.0"
)

# Конфигуриране на статични файлове и шаблони
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
except Exception as e:
    logger.error(f"Грешка при конфигуриране на статични файлове и шаблони: {str(e)}")
    # Опитваме с абсолютни пътища
    try:
        if os.path.exists("/app"):
            app.mount("/static", StaticFiles(directory="/app/static"), name="static")
            templates = Jinja2Templates(directory="/app/templates")
            logger.info("Успешно конфигуриране с абсолютни пътища")
        else:
            raise e
    except Exception as e2:
        logger.error(f"Неуспешно конфигуриране дори с абсолютни пътища: {str(e2)}")
        sys.exit(1)

# Регистриране на маршрутизаторите от модулите
try:
    app.include_router(rtsp_router, prefix="/rtsp", tags=["RTSP Capture"])
    # Регистрираме модул за анализ
    app.include_router(analysis_router, prefix="/analysis", tags=["Image Analysis"])

    # Регистриране на новите PTZ модули
    app.include_router(ptz_control_router, prefix="/ptz/control", tags=["PTZ Control"])
    app.include_router(ptz_capture_router, prefix="/ptz/capture", tags=["PTZ Capture"])
    app.include_router(multi_analysis_router, prefix="/ptz/analysis", tags=["Multi Image Analysis"])
except Exception as e:
    logger.error(f"Грешка при регистриране на маршрутизатори: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главна страница с информация за системата"""
    
    # Вземаме информация от модулите
    rtsp_config = get_capture_config()
    # Добавяме информация от модула за анализ
    analysis_config = get_analysis_config()
    
    # Добавяме информация от новите PTZ модули
    ptz_config = get_ptz_config()
    ptz_capture_config = get_ptz_capture_config()
    multi_analysis_config = get_multi_analysis_config()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "ObzorWeather System",
        "rtsp_config": rtsp_config,
        "analysis_config": analysis_config,
        "ptz_config": ptz_config,
        "ptz_capture_config": ptz_capture_config,
        "multi_analysis_config": multi_analysis_config
    })

@app.get("/health")
async def health():
    """Проверка на здравословното състояние на системата"""
    # Добавяме информация за статуса на новия модул
    analysis_config = get_analysis_config()
    ptz_config = get_ptz_config()
    ptz_capture_config = get_ptz_capture_config()
    multi_analysis_config = get_multi_analysis_config()
    
    # Проверяваме статуса на директориите
    directory_status = {}
    for dir_name in required_dirs:
        if os.path.exists("/app"):
            full_path = os.path.join("/app", dir_name)
        else:
            full_path = dir_name
            
        directory_status[dir_name] = {
            "exists": os.path.exists(full_path),
            "is_writable": os.access(full_path, os.W_OK) if os.path.exists(full_path) else False,
            "path": full_path
        }
        
        # За ptz_frames проверяваме и поддиректориите
        if dir_name == "ptz_frames" and os.path.exists(full_path):
            directory_status[dir_name]["subdirectories"] = {}
            for pos in range(5):
                pos_dir = os.path.join(full_path, f"position_{pos}")
                directory_status[dir_name]["subdirectories"][f"position_{pos}"] = {
                    "exists": os.path.exists(pos_dir),
                    "is_writable": os.access(pos_dir, os.W_OK) if os.path.exists(pos_dir) else False,
                    "path": pos_dir
                }
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "modules": {
            "rtsp_capture": "active",
            "image_analysis": analysis_config.status,
            "ptz_control": ptz_config.status,
            "ptz_capture": ptz_capture_config.status,
            "multi_image_analysis": multi_analysis_config.status
        },
        "directories": directory_status
    }

# Маршрут за пренасочване към последното изображение
@app.get("/latest.jpg")
async def latest_image_redirect():
    return RedirectResponse(url="/rtsp/latest.jpg")

# Маршрут за пренасочване към последното PTZ изображение (позиция 0 - покой)
@app.get("/ptz_latest.jpg")
async def ptz_latest_image_redirect():
    return RedirectResponse(url="/ptz/capture/latest/0.jpg")

if __name__ == "__main__":
    # Настройки от environment променливи
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "7860"))
    
    logger.info(f"Стартиране на ObzorWeather System на {host}:{port}")
    logger.info("Инициализирани модули: RTSP Capture, Image Analysis, PTZ Control, PTZ Capture, Multi Image Analysis")
    
    # Проверка за наличие на Anthropic API ключ
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY не е наличен! Image Analysis модулът няма да работи правилно.")
    
    # Проверка за наличие на Imou API данни
    if not (os.getenv("IMOU_APP_ID") and os.getenv("IMOU_APP_SECRET") and os.getenv("IMOU_DEVICE_SN")):
        logger.warning("IMOU_APP_ID, IMOU_APP_SECRET или IMOU_DEVICE_SN не са налични! PTZ Control модулът ще използва стойности по подразбиране.")
    
    # Информация за пътищата в системата
    logger.info(f"Текуща директория: {os.getcwd()}")
    logger.info(f"Директории: {', '.join(required_dirs)}")
    
    # Стартиране на сървъра
    uvicorn.run(app, host=host, port=port)