import os
import logging
import asyncio
import json
from aiohttp import web
import aiohttp_cors  # Установи: pip install aiohttp-cors
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode

import scheduler
import utils

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Читаем переменные окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
SCHEDULE_URL = os.getenv('SCHEDULE_URL') # Ссылка на страницу ФМиИТ
WEBAPP_URL = os.getenv('WEBAPP_URL')     # Ссылка на твой HTML на Render

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
parser = scheduler.init_parser(SCHEDULE_URL)

# Хранилище групп в памяти (лучше потом заменить на БД или JSON файл)
user_groups = {}

# --- БЛОК API СЕРВЕРА (То, чего у тебя не было) ---

async def run_api_server():
    app = web.Application()
    
    # Настройка CORS для работы с Web App
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    async def get_schedule_api(request):
        data = await parser.get_schedule()
        return web.json_response(data)

    # Регистрация путей
    res_schedule = app.router.add_get('/api/schedule', get_schedule_api)
    app.router.add_get('/', lambda r: web.Response(text="Bot & API are running"))
    
    # Применяем CORS
    cors.add(res_schedule)

    runner = web.AppRunner(app)
    await runner.setup()
    # Render дает порт в переменной окружения PORT
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ API сервер запущен на порту {port}")

# --- ЛОГИКА БОТА ---

def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    # Пытаемся достать группу пользователя для ссылки
    group = user_groups.get(str(user_id), "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🌐 Открыть расписание", 
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?group={group}")
        )],
        [InlineKeyboardButton(text="📅 Моё в чате", callback_data="my_schedule")],
        [InlineKeyboardButton(text="👥 Выбрать группу", callback_data="choose_group")]
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Используй Web App для удобного просмотра или выбери группу ниже:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.callback_query(lambda c: c.data.startswith("group_"))
async def callback_select_group(callback: CallbackQuery):
    group = callback.data.replace("group_", "")
    user_groups[str(callback.from_user.id)] = group
    await callback.answer(f"Выбрана группа: {group}")
    await callback.message.edit_text(
        f"✅ Группа {group} сохранена!", 
        reply_markup=get_main_keyboard(callback.from_user.id)
    )

# ... (остальные хендлеры: choose_group, my_schedule и т.д. из предыдущих версий)

# --- ЗАПУСК ---

async def main():
    # 1. Сначала парсим данные, чтобы кэш не был пустым
    logger.info("Загрузка расписания...")
    await parser.get_schedule(force_refresh=True)

    # 2. Запускаем API сервер фоном
    asyncio.create_task(run_api_server())

    # 3. Запускаем бота
    logger.info("Запуск бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")