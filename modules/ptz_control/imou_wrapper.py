# Файл: modules/ptz_control/imou_wrapper.py
"""
Обвиваща логика около imouapi библиотеката за осигуряване на съвместимост
с различни версии и адаптиране на интерфейса.
"""

import logging
import aiohttp
from typing import Optional, Dict, Any, Tuple

from imouapi.api import ImouAPIClient
from imouapi.device import ImouDevice

class ImouDeviceWrapper:
    """
    Клас, който обвива ImouDevice и предоставя унифициран интерфейс
    независимо от версията на библиотеката.
    """
    
    def __init__(self, app_id: str, app_secret: str, device_sn: str, logger: logging.Logger):
        """Инициализира обвиващия клас с необходимите данни"""
        self.app_id = app_id
        self.app_secret = app_secret
        self.device_sn = device_sn
        self.logger = logger
        self.session = None
        self.api_client = None
        self.device = None
        self.initialized = False
    
    async def initialize(self) -> bool:
        """
        Инициализира връзката с Imou API и устройството
        
        Returns:
            bool: Успешна инициализация или не
        """
        try:
            # Създаваме aiohttp сесия
            self.session = aiohttp.ClientSession()
            
            # Създаваме API клиент
            self.api_client = ImouAPIClient(self.app_id, self.app_secret, self.session)
            
            # Създаваме устройство
            self.device = ImouDevice(self.api_client, self.device_sn)
            
            # Проверяваме връзката с устройството
            connected = await self._test_connection()
            
            if connected:
                self.initialized = True
                return True
            else:
                await self.close()
                return False
                
        except Exception as e:
            self.logger.error(f"Грешка при инициализация на Imou устройство: {str(e)}")
            await self.close()
            return False
    
    async def _test_connection(self) -> bool:
        """
        Проверява връзката с устройството
        
        Returns:
            bool: Успешна връзка или не
        """
        try:
            # Първо опитваме с метода get_device_info (по-нови версии)
            try:
                info = await self.device.get_device_info()
                self.logger.info(f"Успешно получаване на device_info: {info}")
                return True
            except AttributeError:
                # Ако методът не съществува, опитваме други методи
                pass
                
            # Пробваме с get_device_status (някои версии)
            try:
                status = await self.device.get_device_status()
                self.logger.info(f"Успешно получаване на device_status: {status}")
                return True
            except AttributeError:
                # Ако и този метод липсва, опитваме директно управление
                pass
            
            # Накрая опитваме директно преместване към preset
            # Това може да провокира грешка, но ще ни покаже дали устройството отговаря
            try:
                await self.device.go_to_preset(1)
                await self.device.go_to_preset(1)  # Повтаряме, за да сме сигурни
                self.logger.info("Успешно тестово преместване към preset")
                return True
            except Exception as e:
                self.logger.error(f"Грешка при тестово преместване: {str(e)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Грешка при проверка на връзката: {str(e)}")
            return False
    
    async def go_to_preset(self, preset_id: int) -> bool:
        """
        Премества камерата към предварително зададена позиция
        
        Args:
            preset_id: ID на preset позицията
            
        Returns:
            bool: Успешно преместване или не
        """
        if not self.initialized or not self.device:
            self.logger.error("Устройството не е инициализирано")
            return False
            
        try:
            await self.device.go_to_preset(preset_id)
            return True
        except Exception as e:
            self.logger.error(f"Грешка при преместване към preset {preset_id}: {str(e)}")
            return False
    
    async def stop_ptz_movement(self) -> bool:
        """
        Спира текущото движение на камерата
        
        Returns:
            bool: Успешно спиране или не
        """
        if not self.initialized or not self.device:
            self.logger.error("Устройството не е инициализирано")
            return False
            
        try:
            # Проверяваме дали методът съществува
            if hasattr(self.device, 'stop_ptz_movement'):
                await self.device.stop_ptz_movement()
            else:
                # Ако не съществува, опитваме алтернативен подход
                # В случая просто връщаме False, тъй като нямаме директен еквивалент
                self.logger.warning("Методът stop_ptz_movement не е наличен в текущата версия на imouapi")
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"Грешка при спиране на движението: {str(e)}")
            return False
    
    async def close(self):
        """Затваря сесията и освобождава ресурсите"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
                
            self.api_client = None
            self.device = None
            self.initialized = False
        except Exception as e:
            self.logger.error(f"Грешка при затваряне на сесията: {str(e)}")