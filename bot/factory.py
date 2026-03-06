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

logger = logging.getLogger(__name__)

class ScheduleFactory:
    def __init__(self):
        # Словарь соответствия: Ключ - название для бота, Значение - экземпляр класса
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
        # Общий маппинг: "Название_Группы": "Объект_Парсера"
        self.group_to_parser = {}

    async def update_all(self):
        """Обновляет данные всех факультетов параллельно"""
        print("🔄 Начинаю глобальное обновление всех факультетов ВГУ...")
        
        tasks = [parser.refresh() for parser in self.parsers.values()]
        await asyncio.gather(*tasks)
        
        # Строим карту поиска групп
        self.group_to_parser = {}
        for name, parser in self.parsers.items():
            groups = parser.get_groups()
            for g in groups:
                self.group_to_parser[g] = parser
        
        print(f"✅ Обновление завершено! Всего групп в базе: {len(self.group_to_parser)}")

    def get_all_groups(self):
        """Возвращает отсортированный список всех групп университета"""
        return sorted(list(self.group_to_parser.keys()))

    def get_schedule(self, group_name):
        """Находит нужный парсер для группы и возвращает расписание"""
        parser = self.group_to_parser.get(group_name)
        if parser:
            return parser.get_schedule(group_name)
        return None
