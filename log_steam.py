import re
import time
import sys
import winreg
from datetime import datetime
from pathlib import Path
import logging

class SteamDownloadMonitor:
    def __init__(self, log_to_file=True, log_file_path=None):

        self.setup_logging(log_to_file, log_file_path)
        self.logger = logging.getLogger('SteamMonitor')
        self.steam_path = self.get_steam_path()
        self.log_file = self.steam_path / "logs" / "content_log.txt"
        self.current_appid = None
        self.game_name = None
        self.last_check_time = None

    def setup_logging(self, log_to_file=True, log_file_path=None):
        """Настройка системы логирования"""
        logger = logging.getLogger('SteamMonitor')
        logger.setLevel(logging.INFO)

        # Формат сообщений
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Обработчик для консоли
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Обработчик для файла
        if log_to_file:
            if not log_file_path:
                log_file_path = Path(__file__).parent / 'steam_monitor.log'

            file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            logger.info(f"Логирование в файл: {log_file_path}")

    def get_steam_path(self):
        """Получает путь установки Steam из реестра"""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
                self.logger.info(f"Найден Steam в: {steam_path}")
                return steam_path
        except Exception as e:
            self.logger.error(f"Ошибка поиска Steam: {e}")
            # Альтернативный путь
            default_path = Path("C:/Steam")
            if default_path.exists():
                self.logger.info(f"Использую стандартный путь: {default_path}")
                return default_path
            self.logger.error("Steam не найден. Убедитесь, что Steam установлен")
            sys.exit(1)

    def get_game_name_from_manifest(self, appid):
        """Получает название игры из файла манифеста"""
        manifest_file = self.steam_path / "steamapps" / f"appmanifest_{appid}.acf"

        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    # Ищем название игры в манифесте
                    name_match = re.search(r'"name"\s+"([^"]+)"', content)
                    if name_match:
                        return name_match.group(1)
                    else:
                        # Пробуем найти в другом формате
                        name_match = re.search(r'name\s+"([^"]+)"', content)
                        if name_match:
                            return name_match.group(1)
            except Exception as e:
                self.logger.error(f"Ошибка чтения манифеста: {e}")

        # Если не нашли, возвращаем заглушку
        return f"Игра (AppID: {appid})"

    def parse_log_file(self):
        """Парсит лог-файл и извлекает информацию о загрузке"""
        if not self.log_file.exists():
            self.logger.warning(f"Файл логов не найден: {self.log_file}")
            return None, None, None

        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Читаем последние 50 строк
                if len(lines) > 50:
                    lines = lines[-50:]
                else:
                    lines = lines
        except Exception as e:
            self.logger.error(f"Ошибка чтения лог-файла: {e}")
            return None, None, None

        appid = None
        download_speed = None
        status = "неизвестно"

        # Анализируем строки с конца к началу
        for line in reversed(lines):
            # Ищем AppID текущей загрузки
            if appid is None:
                appid_match = re.search(r'AppID\s+(\d+)', line)
                if appid_match:
                    appid = appid_match.group(1)

            # Ищем текущую скорость загрузки
            if download_speed is None:
                speed_match = re.search(r'Current download rate:\s+([\d.]+)\s+Mbps', line)
                if speed_match:
                    download_speed = float(speed_match.group(1))

            # Определяем статус загрузки
            if 'App update changed' in line:
                if 'Downloading' in line:
                    status = 'загружается'
                elif 'Paused' in line:
                    status = 'на паузе'
                elif 'Verifying' in line:
                    status = 'проверка файлов'
                elif 'Preallocating' in line:
                    status = 'подготовка места'
                elif 'Staging' in line:
                    status = 'распаковка'

            # Ищем информацию о размере загрузки
            if 'update started' in line and appid:
                # Пример строки: update started : download 0/24012859376
                size_match = re.search(r'download\s+(\d+)/(\d+)', line)
                if size_match:
                    downloaded = int(size_match.group(1))
                    total = int(size_match.group(2))
                    if total > 0:
                        progress = (downloaded / total) * 100
                        return appid, download_speed, status, progress, downloaded, total

        return appid, download_speed, status, None, None, None

    def format_speed(self, speed_mbps):
        """Форматирует скорость"""
        if speed_mbps is None:
            return "неизвестно"

        if speed_mbps >= 1000:
            return f"{speed_mbps / 1000:.2f} Gbps"
        else:
            return f"{speed_mbps:.2f} Mbps"

    def format_size(self, bytes_size):
        """Форматирует размер в читаемый вид"""
        if bytes_size is None:
            return "неизвестно"

        if bytes_size >= 1024 ** 3:  # GB
            return f"{bytes_size / (1024 ** 3):.2f} GB"
        elif bytes_size >= 1024 ** 2:  # MB
            return f"{bytes_size / (1024 ** 2):.2f} MB"
        elif bytes_size >= 1024:  # KB
            return f"{bytes_size / 1024:.2f} KB"
        else:
            return f"{bytes_size} B"

    def display_info(self, check_number, total_checks):
        """Отображает информацию о загрузке"""
        appid, speed, status, progress, downloaded, total = self.parse_log_file()

        self.logger.info(f"\n{'=' * 80}")
        self.logger.info(f"Проверка {check_number}/{total_checks} - {datetime.now().strftime('%H:%M:%S')}")
        self.logger.info(f"{'=' * 80}")

        if appid:
            # Получаем имя игры, если оно изменилось или еще не получено
            if appid != self.current_appid:
                self.game_name = self.get_game_name_from_manifest(appid)
                self.current_appid = appid

            self.logger.info(f"Игра: {self.game_name}")
            self.logger.info(f"AppID: {appid}")
            self.logger.info(f"Статус: {status}")

            if speed is not None and status == 'загружается':
                self.logger.info(f"Скорость: {self.format_speed(speed)}")

            if progress is not None:
                self.logger.info(f"Прогресс: {progress:.1f}%")
                self.logger.info(f"Загружено: {self.format_size(downloaded)} / {self.format_size(total)}")

            self.logger.info(f"Состояние: {status}")
        else:
            self.logger.info("Нет активных загрузок")

    def monitor(self, duration_minutes=5, interval_seconds=60):
        """Основной цикл мониторинга"""
        self.logger.info(f"\nЗапуск мониторинга загрузок Steam")
        self.logger.info(f"Лог-файл: {self.log_file}")
        self.logger.info(f"Длительность: {duration_minutes} минут")
        self.logger.info(f"Интервал: {interval_seconds} секунд")
        self.logger.info(f"Папка Steam: {self.steam_path}")

        if not self.log_file.exists():
            self.logger.warning(f"\nВнимание: Лог-файл не найден!")
            self.logger.warning("Убедитесь, что Steam запущен и начата загрузка игры.")
            self.logger.warning("Файл должен появиться по пути:", self.log_file)

        total_checks = duration_minutes

        for check_number in range(1, total_checks + 1):
            try:
                self.display_info(check_number, total_checks)

                # ждем если не все
                if check_number < total_checks:
                    self.logger.warning(f"\nСледующая проверка через {interval_seconds} секунд...")
                    for remaining in range(interval_seconds, 0, -10):
                        if remaining % 30 == 0 or remaining <= 10:
                            self.logger.warning(f" Осталось: {remaining} сек")
                        time.sleep(10 if remaining > 10 else remaining)

            except KeyboardInterrupt:
                self.logger.error("\n\nМониторинг прерван пользователем")
                break
            except Exception as e:
                self.logger.error(f"\nОшибка при проверке: {e}")
                time.sleep(interval_seconds)

        self.logger.info(f"\n{'=' * 80}")
        self.logger.info("Мониторинг завершен")


def main():
    """Основная функция"""
    monitor = SteamDownloadMonitor()
    monitor.monitor(duration_minutes=5, interval_seconds=60)


if __name__ == "__main__":
    main()