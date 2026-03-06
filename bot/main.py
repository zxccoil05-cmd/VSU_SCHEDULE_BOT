import asyncio
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from contextlib import asynccontextmanager
import dotenv
import os
from aiogram.client.session.aiohttp import AiohttpSession

from factory import ScheduleFactory

dotenv.load_dotenv()

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')

factory = ScheduleFactory()
logging.basicConfig(level=logging.INFO, format='%(message)s')

# --- ФОНОВАЯ ЗАДАЧА ОБНОВЛЕНИЯ ---

async def schedule_refresher():
    """Фоновый цикл: обновляет данные каждые 6 часов"""
    # Ждем немного перед первым циклом, чтобы не мешать старту сервера
    await asyncio.sleep(10) 
    
    while True:
        try:
            print("🕒 Наступило время планового обновления (раз в 6 часов)...")
            await factory.update_all()
            print("✅ Плановое обновление всех факультетов завершено успешно.")
        except Exception as e:
            print(f"❌ Ошибка при плановом обновлении: {e}")
        
        # Спим 6 часов (6 * 60 * 60 = 21600 секунд)
        await asyncio.sleep(21600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Запускаем немедленное обновление при старте
    asyncio.create_task(factory.update_all())
    
    # 2. Запускаем бесконечный цикл обновления раз в 6 часов
    asyncio.create_task(schedule_refresher())
    
    print("🚀 Фоновое обновление (разовое + циклическое) запущено.")
    yield

# --- ИНИЦИАЛИЗАЦИЯ APP ---

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API ЭНДПОИНТЫ ---

@app.get("/api/faculties")
async def get_facs():
    return {"faculties": list(factory.parsers.keys())}

@app.get("/api/faculties/{fac}/groups")
async def get_groups(fac: str):
    parser = factory.parsers.get(fac)
    if not parser: raise HTTPException(404)
    return {"groups": parser.get_groups()}

@app.get("/api/schedule/{group}")
async def get_sched(group: str):
    sched = factory.get_schedule(group)
    if not sched: raise HTTPException(404)
    return {"schedule": sched}

# --- БОТ ---

session = AiohttpSession(timeout=40)
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📅 Открыть расписание", 
        web_app=WebAppInfo(url=WEBAPP_URL)
    ))
    builder.row(types.InlineKeyboardButton(
        text="⚙️ Настроить в чате", 
        callback_data="setup_chat"
    ))

    await message.answer(
        "<b>🎓 Привет! Это Mini App расписания ВГУ.</b>\n\n"
        "Нажми на кнопку ниже, чтобы открыть приложение.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# --- ЗАПУСК ---

async def main():
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=port, 
        loop="asyncio",
        timeout_keep_alive=0
    )
    server = uvicorn.Server(config)

    print("🤖 Запуск инфраструктуры...")

    server_task = asyncio.create_task(server.serve())
    
    async def start_bot():
        while True:
            try:
                print("🔹 Попытка подключения к Telegram...")
                await dp.start_polling(bot, skip_updates=True)
            except Exception as e:
                print(f"⚠️ Ошибка бота: {e}")
                await asyncio.sleep(5)

    bot_task = asyncio.create_task(start_bot())

    # Ждем завершения сервера
    await server_task

if __name__ == "__main__":
    asyncio.run(main())