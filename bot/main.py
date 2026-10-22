import asyncio
import logging
import uvicorn
import os
import dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Path as ApiPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from contextlib import asynccontextmanager
from aiogram.client.session.aiohttp import AiohttpSession
from pydantic import BaseModel, Field

dotenv.load_dotenv()

from auth import (
    AdminsFileError,
    BlacklistError,
    TelegramInitDataError,
    UserStoreError,
    get_blacklisted_user_ids,
    get_all_users,
    is_user_blacklisted,
    is_user_admin,
    save_user,
    set_user_blacklisted,
    verify_telegram_init_data,
)
from factory import ScheduleFactory

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')

factory = ScheduleFactory()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(alias="initData")

# --- ФОНОВАЯ ЗАДАЧА ОБНОВЛЕНИЯ ---

async def schedule_refresher():
    """Фоновый цикл: обновляет данные каждые 6 часов"""
    while True:
        try:
            print("🕒 Наступило время обновления данных...")
            await factory.update_all()
            print("✅ Обновление завершено успешно.")
        except Exception as e:
            print(f"❌ Ошибка при обновлении: {e}")
        
        # Спим 6 часов ПОСЛЕ успешного или ошибочного обновления
        await asyncio.sleep(21600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запускаем один единственный цикл, который сделает первое обновление СРАЗУ
    refresher_task = asyncio.create_task(schedule_refresher())
    print("🚀 Фоновый сервис обновлений запущен.")
    
    yield
    
    # При выключении сервера отменяем задачу (хороший тон)
    refresher_task.cancel()

# --- ИНИЦИАЛИЗАЦИЯ APP ---

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API ЭНДПОИНТЫ ---

@app.post("/api/auth")
def authenticate_user(payload: TelegramAuthRequest):
    try:
        user = verify_telegram_init_data(payload.init_data, TOKEN)
        user_id = user["id"]
        if is_user_blacklisted(user_id):
            return JSONResponse(
                status_code=403,
                content={
                    "status": "banned",
                    "message": "Доступ к приложению ограничен.",
                },
            )
        admin_status = is_user_admin(user_id)
        saved_user = save_user(user)
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (AdminsFileError, BlacklistError, UserStoreError) as exc:
        logger.exception("Не удалось проверить доступ пользователя Telegram.")
        raise HTTPException(
            status_code=500,
            detail="Не удалось проверить доступ. Попробуйте позже.",
        ) from exc

    return {
        "status": "ok",
        "is_admin": admin_status,
        "user": {
            **saved_user,
            "id": user_id,
            "photo_url": user.get("photo_url"),
        },
    }


def require_active_user(
    init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict:
    try:
        user = verify_telegram_init_data(init_data, TOKEN)
        if is_user_blacklisted(user["id"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "status": "banned",
                    "message": "Доступ к приложению ограничен.",
                },
            )
        return user
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except BlacklistError as exc:
        logger.exception("Не удалось проверить blacklist.txt.")
        raise HTTPException(
            status_code=500,
            detail="Не удалось проверить доступ. Попробуйте позже.",
        ) from exc


def require_admin_user(
    user: dict = Depends(require_active_user),
) -> dict:
    try:
        if not is_user_admin(user["id"]):
            raise HTTPException(
                status_code=403,
                detail="Доступно только администраторам.",
            )
    except AdminsFileError as exc:
        logger.exception("Не удалось проверить admins.txt.")
        raise HTTPException(
            status_code=500,
            detail="Не удалось проверить права администратора.",
        ) from exc
    return user


@app.get("/api/admin/users")
def get_users(user: dict = Depends(require_admin_user)):
    try:
        blocked_ids = get_blacklisted_user_ids()
        users = get_all_users()
    except UserStoreError as exc:
        logger.exception("Не удалось прочитать список пользователей.")
        raise HTTPException(
            status_code=500,
            detail="Не удалось загрузить список пользователей.",
        ) from exc
    except BlacklistError as exc:
        logger.exception("Не удалось прочитать blacklist.txt.")
        raise HTTPException(
            status_code=500,
            detail="Не удалось проверить блокировки пользователей.",
        ) from exc

    return {
        "users": [
            {
                "telegram_id": user.get("telegram_id"),
                "display_name": user.get("display_name"),
                "first_name": user.get("first_name"),
                "username": user.get("username"),
                "created_at": user.get("created_at"),
                "is_blocked": user.get("telegram_id") in blocked_ids,
            }
            for user in users
        ]
    }


@app.post("/api/admin/users/{user_id}/block")
def block_user(
    user_id: int = ApiPath(gt=0),
    admin: dict = Depends(require_admin_user),
):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать собственный аккаунт.")
    try:
        set_user_blacklisted(user_id, True)
    except BlacklistError as exc:
        logger.exception("Не удалось заблокировать пользователя %s.", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"user_id": user_id, "is_blocked": True}


@app.post("/api/admin/users/{user_id}/unblock")
def unblock_user(
    user_id: int = ApiPath(gt=0),
    admin: dict = Depends(require_admin_user),
):
    try:
        set_user_blacklisted(user_id, False)
    except BlacklistError as exc:
        logger.exception("Не удалось разблокировать пользователя %s.", user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"user_id": user_id, "is_blocked": False}


@app.get("/api/faculties")
async def get_facs(user: dict = Depends(require_active_user)):
    return {"faculties": list(factory.parsers.keys())}

@app.get("/api/faculties/{fac}/groups")
async def get_groups(fac: str, user: dict = Depends(require_active_user)):
    parser = factory.parsers.get(fac)
    if not parser: raise HTTPException(404)
    return {"groups": parser.get_groups()}

@app.get("/api/schedule/{group}")
async def get_sched(group: str, user: dict = Depends(require_active_user)):
    sched = factory.get_schedule(group)
    if not sched: raise HTTPException(404)
    return {"schedule": sched}

# НОВЫЙ ЭНДПОИНТ: ПОИСК ПО ПРЕПОДАВАТЕЛЮ
@app.get("/api/teacher/{name}")
async def search_teacher(name: str, user: dict = Depends(require_active_user)):
    query = name.lower().strip()
    if len(query) < 3:
        raise HTTPException(400, "Минимум 3 символа для поиска")

    teacher_schedule = {}
    
    # Проходим по всем факультетам и их группам в памяти
    for fac_name, parser in factory.parsers.items():
        for group in parser.get_groups():
            sched = factory.get_schedule(group)
            if not sched: continue
            
            for day, lessons in sched.items():
                for lesson in lessons:
                    # Ищем совпадение в поле преподавателя
                    current_teacher = lesson.get('teacher', '').lower()
                    if query in current_teacher:
                        if day not in teacher_schedule:
                            teacher_schedule[day] = []
                        
                        # Создаем копию занятия для безопасного изменения
                        lesson_info = lesson.copy()
                        lesson_info['group'] = group
                        
                        # Проверяем на дубликаты (чтобы не дублировать потоковые лекции)
                        duplicate = next((l for l in teacher_schedule[day] 
                                        if l['time'] == lesson_info['time'] and 
                                           l['name'] == lesson_info['name']), None)
                        
                        if duplicate:
                            # Если такая пара уже есть, просто дописываем еще одну группу
                            if group not in duplicate['group']:
                                duplicate['group'] += f", {group}"
                        else:
                            teacher_schedule[day].append(lesson_info)

    # Сортировка по времени
    for day in teacher_schedule:
        teacher_schedule[day].sort(key=lambda x: x.get('time', ''))

    return {"schedule": teacher_schedule}

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

    server_task = asyncio.create_task(server.serve())
    
    async def start_bot():
        while True:
            try:
                await dp.start_polling(bot, skip_updates=True)
            except Exception as e:
                await asyncio.sleep(5)

    bot_task = asyncio.create_task(start_bot())
    await server_task

if __name__ == "__main__":
    asyncio.run(main())