"""
Основна логика за захващане на кадри от RTSP поток
"""

import os
import cv2
import time
import threading
from datetime import datetime
import numpy as np
from PIL import Image
from io import BytesIO

from .config import get_capture_config, update_capture_config
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("rtsp_capture")

def capture_frame() -> bool:
    """Извлича един кадър от RTSP потока и го записва като JPEG файл"""
    config = get_capture_config()
    
    try:
        logger.info(f"Опит за свързване с RTSP поток: {config.rtsp_url}")
        
        # Създаваме VideoCapture обект директно с FFMPEG backend
        cap = cv2.VideoCapture(config.rtsp_url, cv2.CAP_FFMPEG)
        
        # Проверяваме дали потокът е отворен
        if not cap.isOpened():
            logger.error(f"Не може да се отвори RTSP потока: {config.rtsp_url}")
            update_capture_config(status="error")
            return False
        
        logger.info("RTSP потокът е отворен успешно")
        
        # Конфигурация за по-добра работа
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Четем кадъра със 5-секунден таймаут
        has_frame = False
        start_time = time.time()
        frame = None
        
        while not has_frame and time.time() - start_time < 5:
            ret, frame = cap.read()
            if ret and frame is not None:
                has_frame = True
                break
            time.sleep(0.1)
        
        # Освобождаваме ресурсите
        cap.release()
        
        if not has_frame or frame is None:
            logger.error("Не може да се прочете кадър от RTSP потока")
            update_capture_config(status="error")
            return False
        
        # Преоразмеряваме кадъра, ако е нужно
        if config.width > 0 and config.height > 0:
            frame = cv2.resize(frame, (config.width, config.height))
        
        # Генерираме име на файла с текущата дата и час
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"frame_{timestamp}.jpg"
        filepath = os.path.join(config.save_dir, filename)
        
        # Записваме кадъра като JPEG файл
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, config.quality]
        cv2.imwrite(filepath, frame, encode_params)
        
        # Също така записваме кадъра като latest.jpg за лесен достъп
        latest_path = os.path.join(config.save_dir, "latest.jpg")
        cv2.imwrite(latest_path, frame, encode_params)
        
        # Обновяваме конфигурацията
        update_capture_config(
            last_frame_path=filepath,
            last_frame_time=datetime.now(),
            status="ok"
        )
        
        logger.info(f"Успешно запазен кадър в: {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Грешка при извличане на кадър: {str(e)}")
        update_capture_config(status="error")
        return False

def get_placeholder_image() -> bytes:
    """Създава placeholder изображение, когато няма наличен кадър"""
    config = get_capture_config()
    
    # Създаване на празно изображение с текст
    placeholder = np.zeros((config.height, config.width, 3), dtype=np.uint8)
    
    # Добавяне на текст в зависимост от статуса
    if config.status == "initializing":
        message = "Waiting for first frame..."
    elif config.status == "error":
        message = "Error: Could not capture frame"
    else:
        message = "No image available"
    
    # Добавяне на текст към изображението
    cv2.putText(
        placeholder, 
        message, 
        (50, config.height // 2),
        cv2.FONT_HERSHEY_SIMPLEX, 
        1, 
        (255, 255, 255), 
        2
    )
    
    # Конвертиране към bytes
    is_success, buffer = cv2.imencode(".jpg", placeholder)
    if is_success:
        return BytesIO(buffer).getvalue()
    else:
        # Връщаме празен BytesIO, ако не успеем да кодираме
        return BytesIO().getvalue()

def capture_loop():
    """Основен цикъл за периодично извличане на кадри"""
    config = get_capture_config()
    
    while config.running:
        try:
            capture_frame()
        except Exception as e:
            logger.error(f"Неочаквана грешка в capture_loop: {str(e)}")
        
        # Обновяваме конфигурацията (за случай, че е променена)
        config = get_capture_config()
        
        # Спим до следващото извличане
        time.sleep(config.interval)

# Инициализиране на capture_thread
capture_thread = None

def start_capture_thread():
    """Стартира фонов процес за извличане на кадри"""
    global capture_thread
    
    if capture_thread is None or not capture_thread.is_alive():
        capture_thread = threading.Thread(target=capture_loop)
        capture_thread.daemon = True
        capture_thread.start()
        logger.info("Capture thread started")
        return True
    
    return False

def stop_capture_thread():
    """Спира фоновия процес за извличане на кадри"""
    update_capture_config(running=False)
    logger.info("Capture thread stopping")
    return True

# Създаваме placeholder image file при стартиране
def initialize():
    """Инициализира модула"""
    config = get_capture_config()
    
    # Създаваме директорията ако не съществува
    os.makedirs(config.save_dir, exist_ok=True)
    
    # Създаваме placeholder за latest.jpg ако не съществува
    latest_path = os.path.join(config.save_dir, "latest.jpg")
    if not os.path.exists(latest_path):
        placeholder = np.zeros((config.height, config.width, 3), dtype=np.uint8)
        cv2.putText(
            placeholder, 
            "Waiting for first frame...", 
            (50, config.height // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 
            1, 
            (255, 255, 255), 
            2
        )
        cv2.imwrite(latest_path, placeholder)
    
    # Опитваме се да извлечем първия кадър
    initial_result = capture_frame()
    logger.info(f"Резултат от първото извличане: {'успешно' if initial_result else 'неуспешно'}")
    
    # Стартиране на capture thread
    start_capture_thread()
    
    return True

# Автоматично инициализиране при import
initialize()