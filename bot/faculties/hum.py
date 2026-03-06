import openpyxl
import requests
from io import BytesIO
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class HumParser:
    def __init__(self):
        # Актуальная ссылка на Гуманитарный факультет
        self.base_page_url = "https://vsu.by/universitet/fakultety/fakultet-gumanitarnogo-znaniya-i-kommunikacij/raspisanie.html"
        self.cache = {}

    def _get_value(self, sheet, row, col):
        for merged in sheet.merged_cells.ranges:
            if row in range(merged.min_row, merged.max_row + 1) and \
               col in range(merged.min_col, merged.max_col + 1):
                return sheet.cell(row=merged.min_row, column=merged.min_col).value
        return sheet.cell(row=row, column=col).value

    async def _find_all_links(self):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(self.base_page_url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            found_urls = []
            # Исключаем заочку, зачеты и вечернюю форму, если она есть
            black_list = ["заоч", "зфо", "зфпо", "зачет", "экзамен", "сессия", "магистр"]

            for l in links:
                text = l.get_text(separator=" ", strip=True).lower()
                href = l['href'].lower()
                
                if "расписание" in text and (".xlsx" in href or ".xls" in href):
                    if not any(word in text for word in black_list) and \
                       not any(word in href for word in black_list):
                        full_url = urljoin(self.base_page_url, l['href'])
                        found_urls.append(full_url)
            
            return list(set(found_urls))
        except Exception as e:
            logger.error(f"Ошибка поиска ссылок ГФ: {e}")
            return []

    async def refresh(self):
        links = await self._find_all_links()
        if not links:
            logger.error("❌ Файлы расписания ГФ не найдены!")
            return None

        all_fac_data = {}
        
        for url in links:
            try:
                logger.info(f"📥 Обработка файла ГФ: {url}")
                response = requests.get(url)
                wb = openpyxl.load_workbook(BytesIO(response.content), data_only=True)
                sheet = wb.active
                
                subgroups = {}
                group_row = 14
                # У гуманитариев шапка может быть чуть выше или ниже из-за длинных названий
                for r_check in [13, 14, 15, 12, 11]:
                    for col in range(4, sheet.max_column + 1):
                        name = sheet.cell(row=r_check, column=col).value
                        if name and len(str(name).strip()) > 2:
                            if not any(x in str(name) for x in ["Дни", "Часы", "№", "Курс"]):
                                subgroups[col] = str(name).strip()
                    if subgroups:
                        group_row = r_check
                        break
                
                if not subgroups: continue

                for col_idx, sg_name in subgroups.items():
                    if sg_name not in all_fac_data:
                        all_fac_data[sg_name] = {}
                    
                    current_day = "Неизвестно"
                    r = group_row + 1
                    while r < 350:
                        day_val = str(self._get_value(sheet, r, 1) or "").strip()
                        if not day_val:
                            day_val = str(self._get_value(sheet, r, 2) or "").strip()
                            
                        if day_val in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']:
                            current_day = day_val
                            if current_day not in all_fac_data[sg_name]:
                                all_fac_data[sg_name][current_day] = []

                        pair_num = str(self._get_value(sheet, r, 3) or "").strip()
                        if pair_num.isdigit():
                            subject = self._get_value(sheet, r, col_idx)
                            if subject:
                                time_raw = str(self._get_value(sheet, r + 1, 3) or "")
                                teacher = self._get_value(sheet, r + 1, col_idx)
                                room = self._get_value(sheet, r + 2, col_idx)
                                
                                all_fac_data[sg_name][current_day].append({
                                    "time": time_raw.replace("(", "").replace(")", "").strip(),
                                    "name": str(subject).strip().replace('\n', ' '),
                                    "teacher": str(teacher).strip() if teacher else "---",
                                    "room": str(room).strip() if room else "---"
                                })
                            r += 3
                        else:
                            r += 1
            except Exception as e:
                logger.error(f"⚠️ Ошибка в файле ГФ {url}: {e}")

        self.cache = all_fac_data
        logger.info(f"✅ ГФ обновлен. Групп всего: {len(all_fac_data)}")
        return all_fac_data

    def get_groups(self):
        return sorted(list(self.cache.keys())) if self.cache else []

    def get_schedule(self, group_name):
        return self.cache.get(group_name, {}) if self.cache else {}
