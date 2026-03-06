import asyncio
import logging
# Импортируем твой класс (предположим, файл называется vsu_parser.py)
# Если код парсера в этом же файле, удали строку ниже
from faculties.fmiit import FMIiT_Parser 

# Настройка логов, чтобы видеть процесс поиска ссылки и скачивания
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def run_test():
    # 1. URL страницы с расписанием ФМиИТ
    target_url = "https://vsu.by/universitet/fakultety/matematiki-i-it/raspisanie.html"
    
    print("🚀 Инициализация парсера...")
    parser = FMIiT_Parser(target_url)

    print("⏳ Загрузка и обработка файла (это может занять до 30 секунд)...")
    schedule_data = await parser.get_schedule(force_refresh=True)

    if not schedule_data:
        print("❌ Ошибка: Расписание не загружено или пустой кэш.")
        return

    # 2. Выводим список всех найденных групп/подгрупп
    groups = parser.get_groups()
    print(f"\n✅ Найдено подгрупп: {len(groups)}")
    print(f"Список групп: {', '.join(groups[:10])}...") # Показываем первые 10

    # 3. Выбор группы для теста
    # Можно заменить на input(), если хочешь вводить вручную
    target_group = groups[0] # Берем самую первую из списка для теста
    print(f"\n📅 ДЕТАЛЬНОЕ РАСПИСАНИЕ ДЛЯ ГРУППЫ: {target_group}")
    print("=" * 60)

    group_schedule = schedule_data.get(target_group, {})

    if not group_schedule:
        print(f"Пустое расписание для группы {target_group}")
        return

    # Проходим по дням недели
    days_order = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    for day in days_order:
        lessons = group_schedule.get(day, [])
        print(f"\n🟡 {day.upper()}:")
        
        if not lessons:
            print("  --- Пары отсутствуют ---")
            continue

        for i, lesson in enumerate(lessons, 1):
            print(f"  {i}. [{lesson['time']}] {lesson['name']}")
            print(f"     👨‍🏫 Преподаватель: {lesson['teacher']}")
            print(f"     📍 Аудитория: {lesson['room']}")
            print("-" * 30)

    print("\n🏁 ТЕСТ ЗАВЕРШЕН")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        pass
