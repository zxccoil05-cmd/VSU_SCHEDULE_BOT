import asyncio
import logging
from scheduler import MultiFacultyParser

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def run_test():
    # Настройки
    TARGET_FACULTY = "ФМиИТ"
    FACULTY_URL = "https://vsu.by/universitet/fakultety/matematiki-i-it/raspisanie.html"
    
    # Можешь вписать любую группу из своего списка, например "24ПИ1д(24ПИ1д_1)"
    CHECK_GROUP = "24ПИ1д(24ПИ1д_1)" 

    parser = MultiFacultyParser({TARGET_FACULTY: FACULTY_URL})
    print("⏳ Загрузка и парсинг...")
    await parser.refresh_all()
    
    data = await parser.get_faculty_schedule(TARGET_FACULTY)
    groups = parser.get_groups_list(TARGET_FACULTY)

    if not data:
        print("❌ Ошибка: Данные не найдены!")
        return

    print(f"\n✅ Найдено подгрупп: {len(groups)}")
    
    # Если искомой группы нет, берем первую из списка
    target = CHECK_GROUP if CHECK_GROUP in data else groups[0]
    
    print(f"\n📅 РЕЗУЛЬТАТ ДЛЯ ГРУППЫ: {target}")
    print("="*60)
    
    for day, lessons in data[target].items():
        if lessons:
            print(f"\n🟡 {day.upper()}")
            for i, res in enumerate(lessons, 1):
                # Выводим время и название
                time_str = f"[{res['time']}]" if res['time'] else "[--:--]"
                print(f"  {i}. {time_str} {res['name']}")
        else:
            print(f"\n⚪️ {day.upper()}: Пары отсутствуют")

    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(run_test())