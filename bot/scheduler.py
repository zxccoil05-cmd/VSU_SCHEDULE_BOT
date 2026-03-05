import openpyxl
import requests
import logging
from bs4 import BeautifulSoup
from io import BytesIO
import re

logger = logging.getLogger(__name__)

class MultiFacultyParser:
    def __init__(self, faculties_config):
        self.faculties = faculties_config
        self.cache = {} 

    async def refresh_all(self):
        logger.info("🚀 ЗАПУСК ОБНОВЛЕНИЯ...")
        for name, url in self.faculties.items():
            data = await self._parse_faculty_page(name, url)
            if data:
                self.cache[name] = data
                logger.info(f"✅ {name}: Данные обновлены.")

    async def _parse_faculty_page(self, fac_name, page_url):
        try:
            res = requests.get(page_url, timeout=10)
            soup = BeautifulSoup(res.content, 'html.parser')
            links = []
            for a in soup.find_all('a', href=True):
                href, text = a['href'].lower(), a.get_text().lower()
                if ('.xls' in href or '.xlsx' in href) and 'расписание' in text:
                    if any(bad in text for bad in ['заоч', 'экзам']): continue
                    full_url = "https://vsu.by" + a['href'] if a['href'].startswith('/') else a['href']
                    links.append(full_url)
            
            all_data = {}
            for link in list(set(links)):
                file_data = self._parse_excel_file(link)
                if file_data: all_data.update(file_data)
            return all_data
        except Exception as e:
            logger.error(f"Ошибка страницы: {e}")
            return None

    def _get_merged_val(self, sheet, row, col):
        try:
            cell = sheet.cell(row=row, column=col)
            for r in sheet.merged_cells.ranges:
                if cell.coordinate in r:
                    return str(sheet.cell(row=r.min_row, column=r.min_col).value or "").strip()
            return str(cell.value or "").strip()
        except: return ""

    def _parse_excel_file(self, url):
        try:
            res = requests.get(url, timeout=20)
            wb = openpyxl.load_workbook(BytesIO(res.content), data_only=True)
            sheet = wb.active
            found_data = {}

            max_c = min(sheet.max_column, 60)
            for c in range(4, max_c + 1):
                g_val = self._get_merged_val(sheet, 13, c)
                if not g_val or not re.search(r'\d', g_val) or len(g_val) > 20:
                    continue

                raw_sub = str(sheet.cell(row=14, column=c).value or "").strip()
                
                # Если есть инфа о подгруппе (цифра или текст)
                if raw_sub and raw_sub != "None":
                    sub_match = re.search(r'\d+', raw_sub)
                    sub_label = sub_match.group(0) if sub_match else raw_sub
                    key = f"{g_val} ({sub_label})"
                else:
                    # Если ячейка пустая, но это первая колонка для этой группы
                    key = g_val

                lessons = self._extract_lessons(sheet, c, 15)
                if lessons:
                    # Если мы уже нашли версию группы с (2), а текущая без метки - пометим её как (1)
                    if key == g_val and f"{g_val} (2)" in found_data:
                        key = f"{g_val} (1)"
                    # И наоборот
                    if f"{g_val} (2)" == key and g_val in found_data:
                        old_val = found_data.pop(g_val)
                        found_data[f"{g_val} (1)"] = old_val

                    found_data[key] = lessons
            
            return found_data
        except Exception as e:
            logger.error(f"Ошибка файла: {e}")
            return None

    def _extract_lessons(self, sheet, col, start_row):
        sched = {"Понедельник":[], "Вторник":[], "Среда":[], "Четверг":[], "Пятница":[], "Суббота":[]}
        cur_day = None

        def format_time(cell_value):
            raw = str(cell_value or "").strip()
            if not raw or raw == "None": return ""
            parts = re.findall(r'\d{1,2}[:.]\d{2}', raw)
            if len(parts) >= 2:
                return f"{parts[0].replace('.', ':')}-{parts[1].replace('.', ':')}"
            return ""

        r = start_row
        while r < 145:
            row_inc = 1
            day_candidate = self._get_merged_val(sheet, r, 1).capitalize()
            if not day_candidate:
                day_candidate = self._get_merged_val(sheet, r, 2).capitalize()
            
            if day_candidate in sched:
                cur_day = day_candidate

            l1 = str(sheet.cell(row=r, column=col).value or "").strip()
            
            if cur_day and l1 and l1 != "None" and len(l1) > 2:
                if not any(x in l1.lower() for x in ["____", "декан", "утвержд"]):
                    time_v = ""
                    for t_row in [r, r-1, r+1, r-2, r+2]:
                        try:
                            time_v = format_time(sheet.cell(row=t_row, column=3).value)
                            if time_v: break
                        except: continue

                    l2 = str(sheet.cell(row=r+1, column=col).value or "").strip()
                    l3 = str(sheet.cell(row=r+2, column=col).value or "").strip()

                    full = l1
                    if l2 and l2 != "None" and "ауд" not in l2.lower():
                        full += f" | {l2}"
                    
                    aud = ""
                    if "ауд" in l2.lower(): aud = l2
                    elif "ауд" in l3.lower(): aud = l3
                    if aud: full += f" ({aud})"
                    
                    sched[cur_day].append({"time": time_v, "name": full})
                    row_inc = 3
            
            r += row_inc
                
        return sched if any(len(v) > 0 for v in sched.values()) else None

    def get_groups_list(self, fac):
        return sorted(list(self.cache.get(fac, {}).keys()))

    async def get_faculty_schedule(self, fac):
        return self.cache.get(fac, {})