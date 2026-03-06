import asyncio
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from contextlib import asynccontextmanager
import dotenv
import os
from aiogram.client.session.aiohttp import AiohttpSession
import aiohttp

# Настраиваем сессию с увеличенными тайм-аутами
# Это поможет, если сеть на Render подтормаживает


# Твоя фабрика
from factory import ScheduleFactory

dotenv.load_dotenv()
# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv('BOT_TOKEN')
# URL твоего приложения (для локальных тестов через ngrok укажи его здесь)
WEBAPP_URL = os.getenv('WEBAPP_URL')

factory = ScheduleFactory()
logging.basicConfig(level=logging.INFO, format='%(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # КЛЮЧЕВОЙ МОМЕНТ: 
    # Используем create_task, чтобы парсинг ушел в фон.
    # Это позволит lifespan завершиться МГНОВЕННО, 
    # и сервер uvicorn сразу откроет порт 10000.
    asyncio.create_task(factory.update_all())
    print("🚀 Фоновое обновление запущено. Порт открывается...")
    yield

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

# Если хочешь, чтобы FastAPI отдавал index.html (положи их в папку web)
# app.mount("/", StaticFiles(directory="web", html=True), name="web")

# --- БОТ ---

session = AiohttpSession(
    timeout=40, # увеличиваем время ожидания ответа от Telegram
    proxy=None
)

# Инициализируем бота с этой сессией
bot = Bot(
    token=TOKEN, 
    session=session
)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    
    # Главная кнопка открытия Web App
    builder.row(types.InlineKeyboardButton(
        text="📅 Открыть расписание", 
        web_app=WebAppInfo(url=WEBAPP_URL)
    ))
    
    # Кнопка настроек внутри чата (запасной вариант)
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

    # Создаем задачи по отдельности
    server_task = asyncio.create_task(server.serve())
    
    # Запуск бота с бесконечным рестартом при ошибках сети
    async def start_bot():
        while True:
            try:
                print("🔹 Попытка подключения к Telegram...")
                await dp.start_polling(bot, skip_updates=True)
            except Exception as e:
                print(f"⚠️ Ошибка бота (таймаут или сеть): {e}")
                print("🔄 Переподключение через 5 секунд...")
                await asyncio.sleep(5)

    bot_task = asyncio.create_task(start_bot())

    # Ждем только сервер. Если бот упадет — сервер продолжит жить!
    await server_task

if __name__ == "__main__":
    asyncio.run(main())