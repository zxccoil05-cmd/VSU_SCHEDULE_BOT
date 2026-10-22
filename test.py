import requests
from bs4 import BeautifulSoup
import json

# URL страницы электронного расписания ВГУ
URL = "https://vsu.by/studentam/elektronnoe-raspisanie.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://vsu.by/studentam/elektronnoe-raspisanie.html",
}

def parse_vsu_schedule_structure():
    # Используем сессию, чтобы сохранять куки и состояние между запросами
    session = requests.Session()
    session.headers.update(HEADERS)

    print("1. Получаем главную страницу расписания...")
    response = session.get(URL)
    if response.status_code != 200:
        print(f"Ошибка загрузки: статус {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    # Ищем выпадающий список факультетов (<select>)
    # Имя атрибута name может быть faculty_id или содержать слово faculty
    faculty_select = soup.find('select', {'name': lambda x: x and 'faculty' in x.lower()})
    
    if not faculty_select:
        print("Не удалось найти селект факультетов. Проверьте атрибуты name в HTML страницы.")
        return

    faculties = {}
    for option in faculty_select.find_all('option'):
        val = option.get('value')
        text = option.text.strip()
        if val and val != "0" and "выберите" not in text.lower():
            faculties[text] = val

    print(f"Найдено факультетов: {len(faculties)}")

    full_structure = {}

    # 2. Обходим каждый факультет
    for fac_name, fac_id in faculties.items():
        print(f"-> Парсим факультет: {fac_name} (ID: {fac_id})")
        
        full_structure[fac_name] = {
            "faculty_id": fac_id,
            "groups": {}
        }

        # Имитируем отправку формы с выбранным факультетом
        payload = {
            "faculty_id": fac_id
            # Если форма требует другие скрытые поля (например, csrf-токен Joomla), 
            # их тоже нужно будет сюда добавить из HTML страницы.
        }

        # Отправляем POST-запрос на ту же страницу
        res = session.post(URL, data=payload)
        if res.status_code != 200:
            print(f"   Ошибка при запросе факультета {fac_name}")
            continue

        fac_soup = BeautifulSoup(res.text, 'html.parser')

        # Ищем селект групп на обновленной странице
        group_select = fac_soup.find('select', {'name': lambda x: x and 'group' in x.lower()})
        
        if group_select:
            for g_option in group_select.find_all('option'):
                g_val = g_option.get('value')
                g_text = g_option.text.strip()
                if g_val and g_val != "0" and "выберите" not in g_text.lower():
                    full_structure[fac_name]["groups"][g_text] = {
                        "group_id": g_val,
                        # Подгруппы и дни недели обычно зафиксированы в интерфейсе 
                        # или появляются при выборе конкретной группы
                        "subgroups": ["0", "1", "2"], # Стандартные подгруппы (0 - все, 1, 2)
                        "days": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
                    }

    # 3. Сохраняем результат в файл
    output_filename = "vsu_structure.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(full_structure, f, ensure_ascii=False, indent=4)

    print(f"\nГотово! Вся структура успешно сохранена в файл '{output_filename}'.")

if __name__ == "__main__":
    parse_vsu_schedule_structure()