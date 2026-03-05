import logging
import json
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.filters import Command
from bot.scheduler import MultiFacultyParser # Твой исправленный парсер

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 12345678  # Твой ID

# Ссылки на страницы факультетов
FACULTIES = {
    "ФМиИТ": "https://vsu.by/studentu/raspisanie-zanyatij/dnevnaya-forma-obucheniya/fakultet-matematiki-i-informatsionnykh-tekhnologij.html",
    "ФСПиП": "https://vsu.by/studentu/raspisanie-zanyatij/dnevnaya-forma-obucheniya/fakultet-sotsialnoj-pedagogiki-i-psikhologii.html",
    "ЮФ": "https://vsu.by/studentu/raspisanie-zanyatij/dnevnaya-forma-obucheniya/yuridicheskij-fakultet.html",
    # Добавь остальные факультеты сюда
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
parser = MultiFacultyParser(FACULTIES)

# --- РАБОТА С БАЗОЙ (JSON) ---
USER_DATA_FILE = "users.json"

def load_users():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(data):
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_data = load_users()

# --- КЛАВИАТУРЫ ---
def get_main_kb(uid):
    uid = str(uid)
    if uid not in user_data or "group" not in user_data[uid]:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Выбрать факультет", callback_data="start_setup")]
        ])
    
    # Ссылка на твой Web App (замени на свою)
    web_app_url = f"https://твой-сайт.рф/?fac={user_data[uid]['fac']}&group={user_data[uid]['group']}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Моё расписание", web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton(text="🔄 Изменить группу", callback_data="start_setup")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer("Привет! Я бот с расписанием ВГУ.", reply_markup=get_main_kb(m.from_user.id))

@dp.callback_query(F.data == "start_setup")
async def setup_fac(c: CallbackQuery):
    btns = []
    for f in FACULTIES.keys():
        btns.append([InlineKeyboardButton(text=f, callback_data=f"setfac_{f}")])
    await c.message.edit_text("Выбери свой факультет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# 1. Выбор ГРУППЫ (строка 13)
@dp.callback_query(F.data.startswith("setfac_"))
async def setfac(c: CallbackQuery):
    fac = c.data.split("_")[1]
    user_data[str(c.from_user.id)] = {"fac": fac}
    
    groups = parser.get_groups_list(fac)
    if not groups:
        await c.answer("Расписание еще не загружено. Попробуй позже.", show_alert=True)
        return

    btns = []
    row = []
    for i, g in enumerate(groups, 1):
        row.append(InlineKeyboardButton(text=g, callback_data=f"selgrp_{g}"))
        if i % 3 == 0: btns.append(row); row = []
    if row: btns.append(row)
    
    await c.message.edit_text(f"🏢 {fac}. Выбери номер группы:", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# 2. Выбор ПОДГРУППЫ (строка 14)
@dp.callback_query(F.data.startswith("selgrp_"))
async def selgrp(c: CallbackQuery):
    g_name = c.data.split("_")[1]
    uid = str(c.from_user.id)
    fac = user_data[uid]["fac"]
    
    all_fac_data = await parser.get_faculty_schedule(fac)
    
    # Ищем все ключи, которые начинаются с "31 ("
    subgroups = []
    for k in all_fac_data.keys():
        if k.startswith(f"{g_name} ("):
            sub_label = k.split("(")[1].replace(")", "")
            subgroups.append(sub_label)
    
    if not subgroups:
        # Если подгрупп нет, сохраняем просто группу
        user_data[uid]["group"] = g_name
        save_users(user_data)
        await c.message.edit_text(f"✅ Выбрана группа {g_name}", reply_markup=get_main_kb(uid))
        return

    # Показываем ЧИСТЫЕ кнопки подгрупп (1, 2...)
    btns = []
    for s in subgroups:
        btns.append([InlineKeyboardButton(text=f"Подгруппа {s}", callback_data=f"fin_{g_name}_{s}")])
    
    await c.message.edit_text(f"👥 Группа {g_name}. Какая подгруппа?", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# 3. ФИНАЛ
@dp.callback_query(F.data.startswith("fin_"))
async def finish(c: CallbackQuery):
    _, g, s = c.data.split("_")
    uid = str(c.from_user.id)
    # Сохраняем в формате "31 (1)", чтобы парсер нашел в кэше
    user_data[uid]["group"] = f"{g} ({s})"
    save_users(user_data)
    
    await c.message.edit_text(f"✅ Успешно! {g}, подгруппа {s}.", 
                             reply_markup=get_main_kb(uid))

# --- АДМИН-КОМАНДА ОБНОВЛЕНИЯ ---
@dp.message(Command("refresh"))
async def cmd_refresh(m: Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("⏳ Обновляю расписания всех факультетов...")
        await parser.refresh_all()
        await m.answer("✅ Обновление завершено!")

async def main():
    # Первичная загрузка при старте
    await parser.refresh_all()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())