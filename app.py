# Файл: app.py

"""
Основно приложение на ObzorWeather система
Този файл инициализира FastAPI приложението и зарежда всички модули.
"""

import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

from utils.logger import setup_logger

# Инициализиране на логване
logger = setup_logger("app")

# Създаваме FastAPI приложение
app = FastAPI(
    title="ObzorWeather System",
    description="Модулна система за метеорологичен мониторинг",
    version="1.0.0"
)

# Създаваме директории, ако не съществуват
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Конфигуриране на статични файлове и шаблони
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Регистриране на маршрутизаторите от модулите
app.include_router(rtsp_router, prefix="/rtsp", tags=["RTSP Capture"])
# Регистрираме модул за анализ
app.include_router(analysis_router, prefix="/analysis", tags=["Image Analysis"])

# Регистриране на новите PTZ модули
app.include_router(ptz_control_router, prefix="/ptz/control", tags=["PTZ Control"])
app.include_router(ptz_capture_router, prefix="/ptz/capture", tags=["PTZ Capture"])
app.include_router(multi_analysis_router, prefix="/ptz/analysis", tags=["Multi Image Analysis"])

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
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "modules": {
            "rtsp_capture": "active",
            "image_analysis": analysis_config.status,
            "ptz_control": ptz_config.status,
            "ptz_capture": ptz_capture_config.status,
            "multi_image_analysis": multi_analysis_config.status
        }
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
    
    
    # Стартиране на сървъра
    uvicorn.run(app, host=host, port=port)