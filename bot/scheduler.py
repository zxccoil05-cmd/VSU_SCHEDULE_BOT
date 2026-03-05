import openpyxl
import requests
from io import BytesIO
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class VSUParser:
    def __init__(self, base_page_url):
        self.base_page_url = base_page_url
        self.cache = None
        self.last_url = None

    def _get_value(self, sheet, row, col):
        """Пробивает объединенные ячейки (потоковые пары)"""
        for merged in sheet.merged_cells.ranges:
            if row in range(merged.min_row, merged.max_row + 1) and \
               col in range(merged.min_col, merged.max_col + 1):
                return sheet.cell(row=merged.min_row, column=merged.min_col).value
        return sheet.cell(row=row, column=col).value

    async def _find_actual_link(self):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(self.base_page_url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            # Ищем все ссылки
            links = soup.find_all('a', href=True)
            
            for l in links:
                # l.get_text() собирает текст даже из вложенных тегов внутри ссылки
                link_text = l.get_text(separator=" ", strip=True)
                link_href = l['href']
                
                # Проверяем на наличие ключевых слов и расширение
                if "Расписание" in link_text and "занятий" in link_text and ".xlsx" in link_href:
                    full_url = urljoin(self.base_page_url, link_href)
                    logger.info(f"🎯 Ссылка найдена: {full_url}")
                    return full_url
            
            # Если по тексту не нашли, берем ПЕРВУЮ ссылку на xlsx, в которой есть 'ФМиИТ'
            for l in links:
                if ".xlsx" in l['href'] and ("FMiIT" in l['href'] or "ФМиИТ" in l['href']):
                    return urljoin(self.base_page_url, l['href'])

            return None
        except Exception as e:
            logger.error(f"Ошибка краулера: {e}")
            return None

    async def get_schedule(self, force_refresh=False):
        if self.cache and not force_refresh:
            return self.cache

        # Ищем актуальную ссылку
        actual_url = await self._find_actual_link()
        if not actual_url:
            logger.error("Не удалось найти ссылку на файл расписания!")
            return self.cache # Возвращаем старый кэш, если новый не найден

        try:
            logger.info(f"Скачивание файла: {actual_url}")
            response = requests.get(actual_url)
            wb = openpyxl.load_workbook(BytesIO(response.content), data_only=True)
            sheet = wb.active
            
            subgroups = {}
            # Ищем подгруппы в 14-й строке
            for col in range(4, sheet.max_column + 1):
                name = sheet.cell(row=14, column=col).value
                if name and str(name).strip() and len(str(name).strip()) > 1:
                    subgroups[col] = str(name).strip()
            
            final_data = {}
            for col_idx, sg_name in subgroups.items():
                final_data[sg_name] = {}
                current_day = "Неизвестно"
                r = 16
                while r < 350: # Запас по строкам
                    day_val = str(self._get_value(sheet, r, 1) or "").strip()
                    if day_val in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']:
                        current_day = day_val
                        if current_day not in final_data[sg_name]:
                            final_data[sg_name][current_day] = []

                    pair_num = str(self._get_value(sheet, r, 3) or "").strip()
                    if pair_num.isdigit():
                        subject = self._get_value(sheet, r, col_idx)
                        time_raw = str(self._get_value(sheet, r + 1, 3) or "")
                        teacher = self._get_value(sheet, r + 1, col_idx)
                        room = self._get_value(sheet, r + 2, col_idx)
                        
                        if subject:
                            final_data[sg_name][current_day].append({
                                "time": time_raw.replace("(", "").replace(")", "").strip(),
                                "name": str(subject).strip().replace('\n', ' '),
                                "teacher": str(teacher).strip() if teacher else "---",
                                "room": str(room).strip() if room else "---"
                            })
                        r += 3
                    else:
                        r += 1
            
            self.cache = final_data
            self.last_url = actual_url
            return final_data
        except Exception as e:
            logger.error(f"Ошибка парсинга Excel: {e}")
            return self.cache

    def get_groups(self):
        return list(self.cache.keys()) if self.cache else []

def init_parser(url):
    return VSUParser(url)