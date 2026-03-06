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
    print("⏳ Загрузка расписаний ВГУ...")
    await factory.update_all()
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

bot = Bot(token=TOKEN)
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
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, loop="asyncio")
    server = uvicorn.Server(config)
    
    print(f"🚀 API запущен на порту 8000")
    print(f"🤖 Бот запущен!")
    
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())