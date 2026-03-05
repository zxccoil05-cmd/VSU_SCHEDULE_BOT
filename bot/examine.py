import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def debug_find_link():
    url = "https://vsu.by/universitet/fakultety/matematiki-i-it/raspisanie.html"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    print(f"📡 Заходим на {url}...")
    try:
        r = requests.get(url, headers=headers)
        r.encoding = 'utf-8' # На ВГУ обычно utf-8
        soup = BeautifulSoup(r.text, 'html.parser')
        
        links = soup.find_all('a', href=True)
        print(f"🔎 Всего ссылок на странице: {len(links)}")
        
        found = False
        for l in links:
            href = l['href']
            text = l.get_text(strip=True)
            
            # Печатаем всё, что хоть немного похоже на Excel
            if ".xlsx" in href.lower():
                print(f"--- НАЙДЕНО ---")
                print(f"Текст ссылки: '{text}'")
                print(f"URL: {urljoin(url, href)}")
                
                if "Расписание занятий" in text:
                    print("✅ ЭТО ТО, ЧТО НУЖНО!")
                    found = True
        
        if not found:
            print("❌ Ссылка с текстом 'Расписание занятий' не найдена.")
    except Exception as e:
        print(f"💥 Ошибка: {e}")

debug_find_link()