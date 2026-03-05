import os
import logging
import asyncio
import json
import sys
from aiohttp import web
import aiohttp_cors
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BotCommand
from aiogram.enums import ParseMode

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FACULTIES = {
    "ФМиИТ": "https://vsu.by/universitet/fakultety/matematiki-i-it/raspisanie.html",
    "ХБиГН": "https://vsu.by/universitet/fakultety/biologicheskij/raspisanie.html",
    "ПФ": "https://vsu.by/universitet/fakultety/pedagogicheskij-fakultet/raspisanie.html",
    "ФСПиП": "https://vsu.by/universitet/fakultety/sotsialnoj-pedagogiki-i-psikhologii/raspisanie.html",
    "ФФКиС": "https://vsu.by/universitet/fakultety/fizicheskoj-kultury-i-sporta/raspisanie.html",
    "ФГЗиК": "https://vsu.by/universitet/fakultety/fakultet-gumanitarnogo-znaniya-i-kommunikacij/raspisanie.html",
    "ХГФ": "https://vsu.by/universitet/fakultety/khudozhestvenno-graficheskij/raspisanie.html",
    "ЮФ": "https://vsu.by/universitet/fakultety/yuridicheskij/raspisanie.html"
}

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')
DATA_FILE = "user_settings.json"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
parser = scheduler.MultiFacultyParser(FACULTIES)

def load_users():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_users(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_data = load_users()

# --- API FOR WEBAPP ---
async def run_api_server():
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
    
    async def get_schedule_api(request):
        fac = request.query.get('faculty', 'ФМиИТ')
        data = await parser.get_faculty_schedule(fac)
        return web.json_response(data)

    app.router.add_get('/api/schedule', get_schedule_api)
    for r in list(app.router.routes()): cors.add(r)
    
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 10000))).start()

# --- KEYBOARDS ---
def get_main_kb(uid):
    u = user_data.get(str(uid), {"fac": "ФМиИТ", "group": ""})
    url = f"{WEBAPP_URL}?faculty={u['fac']}&group={u['group']}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Открыть расписание", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="⚙️ Сменить настройки", callback_data="change_fac")]
    ])

def get_fac_kb():
    btns = []
    f_list = list(FACULTIES.keys())
    for i in range(0, len(f_list), 2):
        row = [InlineKeyboardButton(text=f_list[i], callback_data=f"setfac_{f_list[i]}")]
        if i+1 < len(f_list): row.append(InlineKeyboardButton(text=f_list[i+1], callback_data=f"setfac_{f_list[i+1]}"))
        btns.append(row)
    return InlineKeyboardMarkup(inline_keyboard=btns)

def get_grp_kb(fac):
    grps = parser.get_groups_list(fac)
    btns = []
    row = []
    for i, g in enumerate(grps, 1):
        # На кнопке отображаем красиво, но в callback шлем полный ключ
        row.append(InlineKeyboardButton(text=g, callback_data=f"setgrp_{g}"))
        if i % 2 == 0: btns.append(row); row = []
    if row: btns.append(row)
    btns.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="change_fac")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

# --- HANDLERS ---
@dp.message(Command("start"))
async def start(m: Message):
    uid = str(m.from_user.id)
    if uid in user_data and user_data[uid].get("group"):
        await m.answer(f"Твой выбор: <b>{user_data[uid]['group']}</b>", reply_markup=get_main_kb(uid))
    else:
        await m.answer("Выбери факультет:", reply_markup=get_fac_kb())

@dp.callback_query(F.data == "change_fac")
async def change(c: CallbackQuery):
    await c.message.edit_text("Выбери факультет:", reply_markup=get_fac_kb())

@dp.callback_query(F.data.startswith("setfac_"))
async def setfac(c: CallbackQuery):
    fac = c.data.split("_")[1]
    user_data[str(c.from_user.id)] = {"fac": fac, "group": ""}
    save_users(user_data)
    await c.message.edit_text(f"Факультет {fac}. Выбери группу:", reply_markup=get_grp_kb(fac))

@dp.callback_query(F.data.startswith("setgrp_"))
async def setgrp(c: CallbackQuery):
    grp = c.data.split("_")[1]
    uid = str(c.from_user.id)
    user_data[uid]["group"] = grp
    save_users(user_data)
    await c.message.edit_text(f"✅ Настроено: <b>{grp}</b>", reply_markup=get_main_kb(uid))

async def main():
    await bot.set_my_commands([BotCommand(command="start", description="Запуск")])
    asyncio.create_task(run_api_server())
    await parser.refresh_all()
    
    # Автообновление раз в 6 часов
    async def auto_update():
        while True:
            await asyncio.sleep(6 * 3600)
            await parser.refresh_all()
    
    asyncio.create_task(auto_update())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())