# Файл: modules/ptz_capture/capture.py
"""
Логика за захващане на кадри от PTZ камера
"""

import os
import cv2
import time
import threading
import asyncio
from datetime import datetime, timedelta
import numpy as np
from PIL import Image
from io import BytesIO

from .config import get_capture_config, update_capture_config
from modules.ptz_control.controller import move_to_position, get_current_position
from utils.logger import setup_logger

# Инициализиране на логър
logger = setup_logger("ptz_capture")

# Глобални променливи
capture_thread = None
last_cycle_start_time = None

def is_active_time() -> bool:
    """
    Проверява дали текущото време е в активния период
    
    Returns:
        bool: В активен период ли сме
    """
    config = get_capture_config()
    
    # Вземаме текущото време
    now = datetime.now().time()
    
    # Прилагаме часова зона и DST ако е необходимо
    # Забележка: Това е грубо, тъй като .time() губи информация за дата
    # По-добро решение би било да се използва pytz или datetime с tzinfo
    
    # Връщаме дали сме в активния период
    return config.active_time_start <= now <= config.active_time_end

def safe_run_coroutine(coro):
    """
    Безопасно изпълнява корутина, дори ако вече има активен event loop
    Актуализирана за Python 3.11
    """
    try:
        if asyncio.iscoroutine(coro):
            # Използваме asyncio.run в Python 3.11, което е по-надеждно
            try:
                # Първо опитваме със съществуващ event loop
                loop = asyncio.get_running_loop()
                # Ако вече има работещ loop, създаваме нов
                new_loop = asyncio.new_event_loop()
                result = new_loop.run_until_complete(coro)
                new_loop.close()
                return result
            except RuntimeError:
                # Ако няма работещ loop, използваме asyncio.run
                return asyncio.run(coro)
        else:
            # Ако не е корутина, връщаме директно стойността
            return coro
    except Exception as e:
        logger.error(f"Грешка при изпълнение на корутина: {str(e)}")
        return False

def capture_position_frame(position_id: int) -> bool:
    """
    Премества камерата към определена позиция и прихваща кадър
    
    Args:
        position_id: ID на позицията (0-4)
        
    Returns:
        bool: Успешно прихващане или не
    """
    config = get_capture_config()
    
    try:
        logger.info(f"Преместване на камерата към позиция {position_id}")
        
        # Преместваме камерата към позицията
        # Използваме безопасното изпълнение на корутини
        move_success = safe_run_coroutine(move_to_position(position_id))
        
        if not move_success:
            logger.error(f"Не може да се премести камерата към позиция {position_id}")
            return False
        
        # Изчакваме стабилизиране на камерата
        logger.info(f"Изчакване на стабилизиране на камерата ({config.position_wait_time} секунди)...")
        time.sleep(config.position_wait_time)
        
        # Прихващаме кадър от RTSP потока
        # Тук използваме URL от RTSP модула, но може да се промени при нужда
        from modules.rtsp_capture.config import get_capture_config as get_rtsp_config
        rtsp_config = get_rtsp_config()
        rtsp_url = rtsp_config.rtsp_url
        
        logger.info(f"Прихващане на кадър от RTSP поток: {rtsp_url}")
        
        # Създаваме VideoCapture обект директно с FFMPEG backend
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        
        # Проверяваме дали потокът е отворен
        if not cap.isOpened():
            logger.error(f"Не може да се отвори RTSP потока: {rtsp_url}")
            return False
        
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
            return False
        
        # Преоразмеряваме кадъра, ако е нужно
        if rtsp_config.width > 0 and rtsp_config.height > 0:
            frame = cv2.resize(frame, (rtsp_config.width, rtsp_config.height))
        
        # Генерираме име на файла с текущата дата и час
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"position_{position_id}_frame_{timestamp}.jpg"
        
        # Определяме директорията за тази позиция
        # Опитваме няколко възможни пътища
        position_dir = None
        paths_to_try = [
            os.path.join(config.save_dir, f"position_{position_id}"),
            os.path.join("ptz_frames", f"position_{position_id}"),
            os.path.join("/app/ptz_frames", f"position_{position_id}")
        ]
        
        for path in paths_to_try:
            try:
                os.makedirs(path, exist_ok=True)
                # Проверяваме дали можем да пишем в директорията
                test_file = os.path.join(path, "test.txt")
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                position_dir = path
                logger.info(f"Успешно използване на директория: {path}")
                break
            except Exception as e:
                logger.warning(f"Не може да се използва директория {path}: {str(e)}")
        
        if position_dir is None:
            logger.error("Не е намерена валидна директория за запазване на кадъра")
            return False
        
        filepath = os.path.join(position_dir, filename)
        
        # Записваме кадъра като JPEG файл
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, rtsp_config.quality]
        cv2.imwrite(filepath, frame, encode_params)
        
        # Също така записваме кадъра като latest.jpg за лесен достъп
        latest_path = os.path.join(position_dir, "latest.jpg")
        cv2.imwrite(latest_path, frame, encode_params)
        
        # Обновяваме конфигурацията с информация за последния кадър
        last_frame_paths = config.last_frame_paths.copy()
        last_frame_paths[position_id] = filepath
        
        update_capture_config(
            last_frame_paths=last_frame_paths,
            last_frame_time=datetime.now(),
            status="ok"
        )
        
        logger.info(f"Успешно запазен кадър за позиция {position_id} в: {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Грешка при прихващане на кадър за позиция {position_id}: {str(e)}")
        return False

def capture_all_positions() -> bool:
    """
    Прихваща кадри от всички дефинирани позиции
    
    Returns:
        bool: Успешно прихващане на всички позиции
    """
    global last_cycle_start_time
    config = get_capture_config()
    last_cycle_start_time = datetime.now()
    
    # Първо проверяваме дали сме в активен период
    if not is_active_time():
        logger.info("Извън активния период, прихващането се пропуска")
        return False
    
    logger.info("Започва цикъл на прихващане на кадри от всички позиции")
    success = True
    
    try:
        # Обхождаме всички дефинирани позиции
        for position_id in config.positions:
            pos_success = capture_position_frame(position_id)
            if not pos_success:
                logger.warning(f"Прихващането на кадър за позиция {position_id} беше неуспешно")
                success = False
        
        # Връщаме камерата в позиция на покой (позиция 0)
        logger.info("Връщане на камерата в позиция на покой")
        safe_run_coroutine(move_to_position(0))
        
        # Ако всичко е OK, обновяваме времето на последния пълен цикъл
        if success:
            update_capture_config(
                last_complete_cycle_time=datetime.now()
            )
            logger.info("Цикълът на прихващане завърши успешно")
        
        return success
    
    except Exception as e:
        logger.error(f"Грешка при цикъл на прихващане: {str(e)}")
        # Опитваме се да върнем камерата в позиция на покой при грешка
        try:
            safe_run_coroutine(move_to_position(0))
        except:
            pass
        return False

def get_placeholder_image() -> bytes:
    """Създава placeholder изображение, когато няма наличен кадър"""
    config = get_capture_config()
    
    # Създаване на празно изображение с текст
    # Използваме размерите от RTSP модула
    from modules.rtsp_capture.config import get_capture_config as get_rtsp_config
    rtsp_config = get_rtsp_config()
    width = rtsp_config.width
    height = rtsp_config.height
    
    placeholder = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Добавяне на текст в зависимост от статуса
    if config.status == "initializing":
        message = "Waiting for first PTZ frame..."
    elif config.status == "error":
        message = "Error: Could not capture PTZ frame"
    else:
        message = "No PTZ image available"
    
    # Добавяне на текст към изображението
    cv2.putText(
        placeholder, 
        message, 
        (50, height // 2),
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
    """Основен цикъл за периодично прихващане на кадри"""
    global last_cycle_start_time
    
    config = get_capture_config()
    
    while config.running:
        try:
            # Проверяваме дали е време за нов цикъл
            current_time = datetime.now()
            
            if last_cycle_start_time is None or (
                current_time - last_cycle_start_time).total_seconds() >= config.interval:
                
                capture_all_positions()
                
        except Exception as e:
            logger.error(f"Неочаквана грешка в capture_loop: {str(e)}")
        
        # Обновяваме конфигурацията (за случай, че е променена)
        config = get_capture_config()
        
        # Спим малко, за да не натоварваме процесора
        # Не спим пълния интервал, за да можем да реагираме на промени в конфигурацията
        time.sleep(10)  # Проверяваме на всеки 10 секунди

def start_capture_thread():
    """Стартира фонов процес за прихващане на кадри"""
    global capture_thread
    
    if capture_thread is None or not capture_thread.is_alive():
        capture_thread = threading.Thread(target=capture_loop)
        capture_thread.daemon = True
        capture_thread.start()
        logger.info("PTZ Capture thread started")
        return True
    
    return False

def stop_capture_thread():
    """Спира фоновия процес за прихващане на кадри"""
    update_capture_config(running=False)
    logger.info("PTZ Capture thread stopping")
    return True

# Функция за инициализиране на модула
def initialize():
    """Инициализира модула"""
    config = get_capture_config()
    
    # Създаваме директориите, ако не съществуват
    # Опитваме няколко възможни пътища
    successful_base_path = None
    paths_to_try = [
        config.save_dir,
        "ptz_frames",
        "/app/ptz_frames"
    ]
    
    for base_path in paths_to_try:
        try:
            os.makedirs(base_path, exist_ok=True)
            
            # Проверяваме дали можем да създаваме файлове
            test_file = os.path.join(base_path, "test_write.txt")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            
            successful_base_path = base_path
            logger.info(f"Успешно използване на базова директория: {base_path}")
            
            # Ако сме намерили работеща директория, актуализираме конфигурацията
            if base_path != config.save_dir:
                update_capture_config(save_dir=base_path)
                logger.info(f"Конфигурацията е актуализирана с нова директория: {base_path}")
            
            break
        except Exception as e:
            logger.warning(f"Не може да се използва директория {base_path}: {str(e)}")
    
    if not successful_base_path:
        logger.error("Не е намерена валидна директория за запазване на кадри. Модулът няма да работи правилно.")
        update_capture_config(status="error")
        return False
    
    # Създаваме поддиректории за позициите
    for pos in config.positions + [0]:  # Включваме и позиция 0 (покой)
        pos_dir = os.path.join(successful_base_path, f"position_{pos}")
        try:
            os.makedirs(pos_dir, exist_ok=True)
            logger.info(f"Създадена директория за позиция {pos}: {pos_dir}")
        except Exception as e:
            logger.error(f"Грешка при създаване на директория за позиция {pos}: {str(e)}")
    
    # Създаваме placeholder изображения, ако е необходимо
    for pos in config.positions + [0]:
        position_dir = os.path.join(successful_base_path, f"position_{pos}")
        latest_path = os.path.join(position_dir, "latest.jpg")
        
        if not os.path.exists(latest_path):
            try:
                # Използваме размерите от RTSP модула
                from modules.rtsp_capture.config import get_capture_config as get_rtsp_config
                rtsp_config = get_rtsp_config()
                width = rtsp_config.width
                height = rtsp_config.height
                
                placeholder = np.zeros((height, width, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder, 
                    f"Waiting for first frame for position {pos}...", 
                    (50, height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    1, 
                    (255, 255, 255), 
                    2
                )
                cv2.imwrite(latest_path, placeholder)
                logger.info(f"Създаден placeholder за позиция {pos}")
            except Exception as e:
                logger.error(f"Грешка при създаване на placeholder за позиция {pos}: {str(e)}")
    
    # Опитваме един цикъл на прихващане
    try:
        capture_all_positions()
    except Exception as e:
        logger.error(f"Грешка при първоначално прихващане: {str(e)}")
    
    # Стартираме thread за прихващане
    start_capture_thread()
    
    logger.info("PTZ Capture модул инициализиран")
    return True

# Автоматично инициализиране при import
initialize()