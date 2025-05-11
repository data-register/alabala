# Файл: modules/ptz_capture/capture.py

import os
import time
import traceback
import datetime
from typing import Optional, List, Dict, Any

import cv2

from utils.logger import setup_logger
from utils.helpers import safe_run_coroutine
from .config import get_capture_config

# Инициализиране на логър
logger = setup_logger("ptz_capture")


def capture_position_frame(position_id: int) -> bool:
    """
    Премества камерата към определена позиция и прихваща кадър
    
    Args:
        position_id: ID на позицията (0-N)
        
    Returns:
        bool: Успешно прихващане или не
    """
    config = get_capture_config()
    
    try:
        logger.info(f"Подготовка за прихващане на кадър от позиция {position_id}")
        
        # Преместваме камерата към позицията
        # ЗАМЕНЕНО: from modules.ptz_control.controller import move_to_position, get_ptz_config
        from modules.ptz_simple.controller import move_to_position, get_ptz_config
        
        # Вземаме PTZ конфигурацията за проверка на пресетите
        ptz_config = get_ptz_config()
        
        # Извикваме move_to_position
        logger.info(f"Преместване на камерата към позиция {position_id}")
        move_success = move_to_position(position_id)
        
        if not move_success:
            logger.error(f"Не може да се премести камерата към позиция {position_id}")
            return False
        
        # Изчакваме стабилизиране на камерата
        logger.info(
            f"Изчакване на стабилизиране на камерата "
            f"({config.position_wait_time} секунди)..."
        )
        time.sleep(config.position_wait_time)
        
        # Прихващаме кадър от RTSP потока
        logger.info(f"Прихващане на кадър от позиция {position_id}")
        
        # Настройваме връзка с RTSP камерата
        rtsp_url = (
            f"rtsp://{config.camera_username}:{config.camera_password}"
            f"@{config.camera_ip}:{config.camera_port}{config.rtsp_path}"
        )
        logger.info(f"Опит за свързване с RTSP поток: {rtsp_url}")
        
        # Отваряме RTSP потока
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            logger.error(f"Не може да се отвори RTSP потока за позиция {position_id}")
            return False
        
        # Прихващаме кадър
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            logger.error(f"Неуспешно прихващане на кадър за позиция {position_id}")
            return False
        
        # Подготвяме име на файла с дата и час
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"position_{position_id}_{timestamp}.jpg"
        
        # Прихващаме кадъра и го запазваме
        position_dir = os.path.join(config.frames_dir, f"position_{position_id}")
        frame_path = os.path.join(position_dir, filename)
        latest_path = os.path.join(position_dir, "latest.jpg")
        
        # Запазваме изображението
        logger.info(f"Запазване на кадър за позиция {position_id} в {frame_path}")
        cv2.imwrite(frame_path, frame)
        
        # Запазваме и като latest.jpg
        cv2.imwrite(latest_path, frame)
        
        logger.info(f"Успешно прихванат кадър за позиция {position_id}")
        return True
        
    except Exception as e:
        logger.error(
            f"Грешка при прихващане на кадър за позиция {position_id}: {str(e)}"
        )
        logger.error(traceback.format_exc())
        return False


def capture_all_positions(exclude_positions: Optional[List[int]] = None) -> Dict[int, bool]:
    """
    Прихваща кадри от всички дефинирани позиции
    
    Args:
        exclude_positions: Списък с позиции, които да се пропуснат
        
    Returns:
        Dict[int, bool]: Речник с резултати за всяка позиция
    """
    config = get_capture_config()
    
    # Зареждаме PTZ конфигурацията за да видим всички позиции
    # ЗАМЕНЕНО: from modules.ptz_control.config import get_ptz_config
    from modules.ptz_simple.config import get_ptz_config
    ptz_config = get_ptz_config()
    
    # Ако не е дефиниран exclude_positions, инициализираме празен списък
    if exclude_positions is None:
        exclude_positions = []
        
    # Намираме всички позиции за прихващане (от конфигурацията на PTZ)
    all_positions = list(ptz_config.positions.keys())
    logger.info(f"Намерени {len(all_positions)} позиции за прихващане: {all_positions}")
    
    # Филтрираме изключените позиции
    positions_to_capture = [
        pos for pos in all_positions if pos not in exclude_positions
    ]
    logger.info(
        f"След филтриране, ще прихванем {len(positions_to_capture)} позиции: "
        f"{positions_to_capture}"
    )
    
    # Резултат от прихващането
    capture_results = {}
    
    # Прихващаме кадри от всяка позиция
    for position_id in positions_to_capture:
        logger.info(f"Прихващане на кадър от позиция {position_id}")
        success = capture_position_frame(position_id)
        capture_results[position_id] = success
        
        # Добавяме пауза между позициите
        if position_id != positions_to_capture[-1]:  # Ако не е последната позиция
            logger.info(
                f"Пауза между позициите ({config.position_transition_time} секунди)"
            )
            time.sleep(config.position_transition_time)
    
    # Връщаме камерата към начална позиция
    if (config.return_to_home and positions_to_capture 
            and 0 not in exclude_positions):
        logger.info("Връщане на камерата към начална позиция")
        # ЗАМЕНЕНО: from modules.ptz_control.controller import move_to_position
        from modules.ptz_simple.controller import move_to_position
        move_to_position(0)
    
    return capture_results


def initialize_capture() -> bool:
    """
    Инициализира модула за прихващане на кадри от PTZ камера
    
    Returns:
        bool: Успешна инициализация или не
    """
    config = get_capture_config()
    
    try:
        logger.info("Инициализиране на PTZ Capture модул")
        
        # Проверяваме дали е достъпна PTZ камерата
        logger.info("Тестване на връзка с PTZ камера")
        
        # Проверяваме дали PTZ контрол модулът е инициализиран
        # ЗАМЕНЕНО: from modules.ptz_control.controller import get_current_position
        from modules.ptz_simple.controller import get_current_position
        position_info = get_current_position()
        logger.info(f"Текуща позиция на камерата: {position_info}")
        
        # Проверяваме дали директориите за кадри съществуват
        logger.info(f"Проверка на директория за кадри: {config.frames_dir}")
        
        if not os.path.exists(config.frames_dir):
            logger.warning(
                f"Директорията {config.frames_dir} не съществува, създаваме я"
            )
            os.makedirs(config.frames_dir)
        
        # Създаваме поддиректории за всяка позиция
        # ЗАМЕНЕНО: from modules.ptz_control.config import get_ptz_config
        from modules.ptz_simple.config import get_ptz_config
        ptz_config = get_ptz_config()
        
        # Проверяваме всички позиции в PTZ конфигурацията
        for position_id in ptz_config.positions.keys():
            position_dir = os.path.join(
                config.frames_dir, f"position_{position_id}"
            )
            
            if not os.path.exists(position_dir):
                logger.info(
                    f"Създаване на директория за позиция {position_id}: "
                    f"{position_dir}"
                )
                os.makedirs(position_dir)
            
            # Проверяваме дали директорията е записваема
            if not os.access(position_dir, os.W_OK):
                logger.error(f"Директорията {position_dir} не е записваема!")
                return False
        
        logger.info("PTZ Capture модул инициализиран успешно")
        return True
        
    except Exception as e:
        logger.error(
            f"Грешка при инициализиране на PTZ Capture модул: {str(e)}"
        )
        logger.error(traceback.format_exc())
        return False


def start_capture_cycle(
    interval_minutes: int = 30,
    exclude_positions: Optional[List[int]] = None
) -> bool:
    """
    Стартира цикличен процес на прихващане
    
    Args:
        interval_minutes: Интервал между циклите в минути
        exclude_positions: Списък с позиции, които да се пропуснат
        
    Returns:
        bool: Успешно стартиране или не
    """
    config = get_capture_config()
    
    # Задаваме интервала
    config.capture_interval = interval_minutes
    
    # Ако цикълът вече работи, спираме го
    if config.capture_running:
        logger.info(
            "Цикълът вече е стартиран, рестартираме го с нови настройки"
        )
        stop_capture_cycle()
    
    # Стартираме цикъла
    logger.info(
        f"Стартиране на цикъл за прихващане с интервал {interval_minutes} минути"
    )
    config.capture_running = True
    config.last_capture_time = None
    config.exclude_positions = exclude_positions or []
    
    # Пускаме първоначално прихващане
    logger.info("Първоначално прихващане на кадри от всички позиции")
    results = capture_all_positions(exclude_positions)
    
    successful = sum(1 for success in results.values() if success)
    logger.info(
        f"Първоначално прихващане: {successful} успешни от {len(results)} позиции"
    )
    
    # Обновяваме времето на последно прихващане
    config.last_capture_time = datetime.datetime.now()
    config.is_capture_cycle_completed = True
    
    logger.info("Цикълът за прихващане е стартиран успешно")
    return True


def stop_capture_cycle() -> bool:
    """
    Спира цикличния процес на прихващане
    
    Returns:
        bool: Успешно спиране или не
    """
    config = get_capture_config()
    
    if not config.capture_running:
        logger.info("Цикълът не е стартиран")
        return True
    
    # Спираме цикъла
    logger.info("Спиране на цикъл за прихващане")
    config.capture_running = False
    
    # Връщаме камерата в позиция 0
    if config.return_to_home:
        logger.info("Връщане на камерата към начална позиция")
        # ЗАМЕНЕНО: from modules.ptz_control.controller import move_to_position
        from modules.ptz_simple.controller import move_to_position
        move_to_position(0)
    
    logger.info("Цикълът за прихващане е спрян успешно")
    return True


def check_capture_cycle() -> Dict[str, Any]:
    """
    Проверява статуса на цикъла и прихваща нови кадри, ако е нужно
    
    Returns:
        Dict[str, Any]: Статус на цикъла
    """
    config = get_capture_config()
    
    # Ако цикълът не е стартиран
    if not config.capture_running:
        return {
            "status": "stopped",
            "message": "Цикълът не е стартиран",
            "next_capture": None,
            "last_capture": config.last_capture_time
        }
    
    # Текущото време
    now = datetime.datetime.now()
    
    # Ако още няма първо прихващане
    if config.last_capture_time is None:
        logger.info("Първоначално прихващане")
        results = capture_all_positions(config.exclude_positions)
        
        successful = sum(1 for success in results.values() if success)
        logger.info(
            f"Прихващане: {successful} успешни от {len(results)} позиции"
        )
        
        config.last_capture_time = now
        config.is_capture_cycle_completed = True
        
        next_capture = now + datetime.timedelta(minutes=config.capture_interval)
        return {
            "status": "running",
            "message": "Първоначално прихващане изпълнено",
            "next_capture": next_capture,
            "last_capture": now,
            "results": results
        }
    
    # Проверяваме дали е време за ново прихващане
    time_since_last = now - config.last_capture_time
    interval_seconds = config.capture_interval * 60
    
    if time_since_last.total_seconds() >= interval_seconds:
        logger.info(
            f"Време за ново прихващане "
            f"(изминали {time_since_last.total_seconds()} секунди)"
        )
        
        results = capture_all_positions(config.exclude_positions)
        
        successful = sum(1 for success in results.values() if success)
        logger.info(
            f"Прихващане: {successful} успешни от {len(results)} позиции"
        )
        
        config.last_capture_time = now
        config.is_capture_cycle_completed = True
        
        next_capture = now + datetime.timedelta(minutes=config.capture_interval)
        return {
            "status": "running",
            "message": "Ново прихващане изпълнено",
            "next_capture": next_capture,
            "last_capture": now,
            "results": results
        }
    else:
        # Изчисляваме оставащото време
        seconds_left = interval_seconds - time_since_last.total_seconds()
        minutes_left = int(seconds_left / 60)
        seconds_remainder = int(seconds_left % 60)
        
        next_capture = config.last_capture_time + datetime.timedelta(
            minutes=config.capture_interval
        )
        
        return {
            "status": "running",
            "message": (
                f"Следващо прихващане след {minutes_left} мин "
                f"{seconds_remainder} сек"
            ),
            "next_capture": next_capture,
            "last_capture": config.last_capture_time,
            "seconds_left": seconds_left
        }