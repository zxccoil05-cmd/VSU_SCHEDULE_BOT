import requests
from bs4 import BeautifulSoup

URL = "https://vsu.by/studentam/elektronnoe-raspisanie.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://vsu.by/studentam/elektronnoe-raspisanie.html",
}

def get_form_options(html_text, select_name):
    """Вспомогательная функция для парсинга <select> по его name"""
    soup = BeautifulSoup(html_text, 'html.parser')
    select_tag = soup.find('select', {'name': select_name})
    options = {}
    if select_tag:
        for opt in select_tag.find_all('option'):
            val = opt.get('value')
            text = opt.text.strip()
            if val and val != "":
                options[text] = val
    return options

def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Загружаем главную страницу расписания
    print("Подключение к сайту ВГУ...")
    res = session.get(URL)
    if res.status_code != 200:
        print(f"Ошибка подключения: {res.status_code}")
        return

    # Получаем факультеты
    faculties = get_form_options(res.text, 'faculty_id')
    fac_names = list(faculties.keys())

    print("\n=== ВЫБОР ФАКУЛЬТЕТА ===")
    for idx, name in enumerate(fac_names, 1):
        print(f"{idx}. {name}")
    
    fac_choice = int(input("\nВведите номер факультета: ")) - 1
    selected_fac_name = fac_names[fac_choice]
    faculty_id = faculties[selected_fac_name]

    # 2. Отправляем выбранный факультет, чтобы сервер вернул актуальный список групп
    print("Загрузка групп для выбранного факультета...")
    payload = {"faculty_id": faculty_id}
    res_fac = session.post(URL, data=payload)
    
    groups = get_form_options(res_fac.text, 'group_id')
    group_names = list(groups.keys())

    print(f"\n=== ГРУППЫ ДЛЯ '{selected_fac_name}' ===")
    for idx, g_name in enumerate(group_names, 1):
        print(f"{idx}. {g_name}")
    
    group_choice = int(input("\nВведите номер группы: ")) - 1
    selected_group_name = group_names[group_choice]
    group_id = groups[selected_group_name]

    # 3. Отправляем факультет и группу, чтобы получить доступные подгруппы для этой группы
    payload = {
        "faculty_id": faculty_id,
        "group_id": group_id
    }
    res_group = session.post(URL, data=payload)
    
    subgroups = get_form_options(res_group.text, 'subgroup_id')
    # Добавим вариант "Все подгруппы" по умолчанию, если его нет
    subgroup_options = {"Все подгруппы": ""}
    subgroup_options.update(subgroups)
    sg_names = list(subgroup_options.keys())

    print("\n=== ВЫБОР ПОДГРУППЫ ===")
    for idx, sg_name in enumerate(sg_names, 1):
        print(f"{idx}. {sg_name}")
    
    sg_choice = int(input("\nВведите номер подгруппы: ")) - 1
    selected_sg_name = sg_names[sg_choice]
    subgroup_id = subgroup_options[selected_sg_name]

    # 4. Выбор типа отображения и дня недели
    print("\n=== ТИП ОТОБРАЖЕНИЯ ===")
    print("1. Расписание на неделю")
    print("2. Расписание на конкретный день")
    view_choice = int(input("\nВыберите вариант (1 или 2): "))

    date_id = ""
    selected_day = "Вся неделя"
    
    if view_choice == 1:
        view_type = "weekly"
    else:
        view_type = "group_day"
        # Дни недели из HTML (151 - Пн, 152 - Вт и т.д.)
        days = {
            "Понедельник": "141",
            "Вторник": "142",
            "Среда": "143",
            "Четверг": "144",
            "Пятница": "145",
            "Суббота": "146"
        }
        day_names = list(days.keys())
        print("\n=== ВЫБОР ДНЯ НЕДЕЛИ ===")
        for idx, day in enumerate(day_names, 1):
            print(f"{idx}. {day}")
        
        day_choice = int(input("\nВведите номер дня недели: ")) - 1
        selected_day = day_names[day_choice]
        date_id = days[selected_day]

    # 5. Финальный запрос расписания
    print(f"\nЗапрос расписания: {selected_group_name} ({selected_day}, подгруппа: {selected_sg_name})...\n")

    final_payload = {
        "faculty_id": faculty_id,
        "group_id": group_id,
        "subgroup_id": subgroup_id,
        "date_id": date_id,
        "view_type": view_type
    }

    response = session.post(URL, data=final_payload)
    if response.status_code != 200:
        print(f"Ошибка сервера: {response.status_code}")
        return

    result_soup = BeautifulSoup(response.text, 'html.parser')
    print(response.text)
    
    # Ищем таблицу с расписанием
    soup = BeautifulSoup(response.text, 'html.parser')

    # Ищем контейнер с расписанием
    schedule_module = soup.find('id', {'id': 'schedule-module'}) # или просто soup.find(id='schedule-module')
    if not schedule_module:
        # Если по id не нашло, ищем просто по тегу или классу, либо берем весь суп
        schedule_module = soup

    # Находим все блоки с подгруппами (заголовки h3 внутри модуля)
    subgroups_blocks = soup.find_all('h3')

    if not subgroups_blocks:
        print("Расписание не найдено или пары отсутствуют.")
    else:
        for h3 in subgroups_blocks:
            subgroup_name = h3.text.strip()
            print(f"\n========================================")
            print(f"ПОДГРУППА: {subgroup_name}")
            print(f"========================================")
            
            # Следующий элемент после h3 — это таблица с расписанием для этой подгруппы
            table = h3.find_next_sibling('table')
            if not table:
                continue
                
            # Проходим по всем строкам таблицы (пропуская заголовок thead)
            rows = table.find_all('tr')
            for row in rows:
                # Извлекаем все ячейки (td)
                cols = row.find_all('td')
                if len(cols) == 4:
                    time_val = cols[0].text.strip()
                    subject = cols[1].text.strip()
                    teacher = cols[2].text.strip()
                    room = cols[3].text.strip()
                    
                    # Выводим только те строки, где есть название предмета
                    if subject:
                        print(f"🕒 {time_val} | 📚 {subject} | 👨‍🏫 {teacher} | 🚪 {room}")

if __name__ == "__main__":
    main()