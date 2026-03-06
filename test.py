import asyncio
import logging

# Выбери, какой парсер тестируем сейчас (просто раскомментируй нужный)
from bot.faculties.ped import PedParser as TestParser
# from bot.parsers.fspip_parser import FSPIPParser as TestParser
# from bot.parsers.gf_parser import GFParser as TestParser

# Настройка логирования, чтобы видеть процесс скачивания
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def run_test():
    print("\n" + "="*60)
    print(f"🧪 ТЕСТИРОВАНИЕ ПАРСЕРА: {TestParser.__name__}")
    print("="*60 + "\n")

    parser = TestParser()

    # 1. Проверяем фильтрацию ссылок
    print("🔎 Шаг 1: Поиск и фильтрация ссылок на Excel...")
    links = await parser._find_all_links()
    
    if not links:
        print("❌ ОШИБКА: Ссылки не найдены! Проверь black_list или base_page_url.")
        return

    print(f"✅ Найдено подходящих файлов: {len(links)}")
    for i, link in enumerate(links, 1):
        print(f"   {i}. {link.split('/')[-1]}")

    # 2. Запускаем парсинг данных
    print("\n📥 Шаг 2: Скачивание и обработка файлов (это может занять время)...")
    data = await parser.refresh()

    if not data:
        print("❌ ОШИБКА: Парсинг завершился с пустым результатом.")
        return

    # 3. Проверяем список групп
    groups = parser.get_groups()
    print(f"\n✅ Шаг 3: Группы успешно извлечены!")
    print(f"📊 Всего найдено групп: {len(groups)}")
    
    # Выводим список групп колонками для удобства
    for i in range(0, len(groups), 4):
        print(" | ".join(f"{g:<15}" for g in groups[i:i+4]))

    # 4. Проверяем содержимое конкретной группы (берем первую из списка)
    if groups:
        target = groups[0]
        print(f"\n📅 Шаг 4: Проверка расписания для группы '{target}':")
        schedule = parser.get_schedule(target)
        
        if not schedule:
            print(f"⚠️  Расписание для группы {target} пустое.")
        else:
            for day, lessons in schedule.items():
                print(f"\n📍 {day}:")
                if not lessons:
                    print("   (нет занятий)")
                for p in lessons:
                    print(f"   [{p['time']}] {p['name']}")
                    print(f"         🏛 {p['room']} | 👨‍🏫 {p['teacher']}")

    print("\n" + "="*60)
    print("🎉 Тест завершен успешно!")
    print("="*60)

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        pass