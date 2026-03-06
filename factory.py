import asyncio
import logging

# Импортируем все твои парсеры
from faculties.fmiit import FMiITParser
from faculties.bio import BioParser
from faculties.sport import SportParser
from faculties.law import LawParser
from faculties.ped import PedParser
from faculties.fspip import FSPIPParser
from faculties.hum import HumParser
from faculties.hgf import HGFParser

# Настраиваем логирование, чтобы видеть INFO сообщения в консоли
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class ScheduleFactory:
    def __init__(self):
        self.parsers = {
            "ФМиИТ": FMiITParser(),
            "ХБиГН": BioParser(),
            "ФФКиС": SportParser(),
            "ЮФ": LawParser(),
            "ПФ": PedParser(),
            "ФСПиП": FSPIPParser(),
            "ГФ": HumParser(),
            "ХГФ": HGFParser()
        }
        self.group_to_parser = {}

    async def update_all(self):
        print("\n" + "="*60)
        print("🚀 ГЛОБАЛЬНОЕ ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ ВГУ")
        print("="*60)
        
        # Запускаем обновление всех парсеров
        # Мы не используем gather, чтобы логи шли по порядку и не перемешивались
        for name, parser in self.parsers.items():
            print(f"\n📡 [ФАКУЛЬТЕТ: {name}]")
            try:
                # В каждом парсере у нас уже есть logger.info("📥 Обработка файла...")
                # Но мы добавим чуть больше конкретики здесь
                data = await parser.refresh()
                
                if data:
                    group_count = len(parser.get_groups())
                    print(f"✅ Успешно: обработано групп — {group_count}")
                else:
                    print(f"⚠️ Предупреждение: файлы найдены, но данные пусты.")
            except Exception as e:
                print(f"❌ ОШИБКА при обновлении {name}: {e}")

        # Строим карту поиска
        self.group_to_parser = {}
        for name, parser in self.parsers.items():
            for g in parser.get_groups():
                self.group_to_parser[g] = parser
        
        print("\n" + "="*60)
        print(f"🏁 ОБНОВЛЕНИЕ ЗАВЕРШЕНО. ВСЕГО ГРУПП: {len(self.group_to_parser)}")
        print("="*60 + "\n")

    def get_all_groups(self):
        return sorted(list(self.group_to_parser.keys()))

    def get_schedule(self, group_name):
        parser = self.group_to_parser.get(group_name)
        return parser.get_schedule(group_name) if parser else None
