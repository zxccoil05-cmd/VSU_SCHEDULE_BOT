import asyncio
import ipaddress
import logging
import os
import threading
import uvicorn
from datetime import datetime, timedelta, timezone
import dotenv
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Path as ApiPath, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from contextlib import asynccontextmanager
from aiogram.client.session.aiohttp import AiohttpSession
from typing import Literal
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
    save_user_vote,
    update_user_activity,
    verify_telegram_init_data,
)
from factory import ScheduleFactory

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')

factory = ScheduleFactory()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
SCHEDULE_REFRESH_INTERVAL_SECONDS = 15 * 60
ACTIVE_USER_TIMEOUT_SECONDS = 90
BROWSER_TEST_MODE = os.getenv("BROWSER_TEST_MODE", "").casefold() == "true"
_activity_lock = threading.Lock()
_last_activity: dict[int, datetime] = {}


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(alias="initData")


class ChannelVoteRequest(BaseModel):
    vote: Literal["yes", "no"]


def is_local_browser_test(request: Request, enabled_header: str) -> bool:
    client = request.client
    if not BROWSER_TEST_MODE or enabled_header.casefold() != "true" or client is None:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        return False


def record_activity(user_id: int) -> datetime:
    now = datetime.now(timezone.utc)
    inactive_before = now - timedelta(days=1)
    with _activity_lock:
        stale_users = [
            active_user_id
            for active_user_id, last_seen in _last_activity.items()
            if last_seen < inactive_before
        ]
        for active_user_id in stale_users:
            del _last_activity[active_user_id]
        _last_activity[user_id] = now
    return now


def get_latest_activity(user_id: int, stored_value: str | None) -> datetime | None:
    with _activity_lock:
        recent = _last_activity.get(user_id)
    if recent is not None:
        return recent
    if stored_value:
        try:
            parsed = datetime.fromisoformat(stored_value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning("Некорректное время активности пользователя %s.", user_id)
    return None


# --- ФОНОВАЯ ЗАДАЧА ОБНОВЛЕНИЯ ---

def schedule_refresher(stop_event: threading.Event) -> None:
    """Refresh schedules on a dedicated thread without blocking the API loop."""
    while not stop_event.is_set():
        try:
            logger.info("Начинаю фоновое обновление расписаний.")
            updated = factory.update_all()
            if updated:
                logger.info("Расписание всех факультетов обновлено.")
            else:
                logger.warning(
                    "Обновление расписания завершено частично; "
                    "для недоступных факультетов сохранены предыдущие данные."
                )
        except Exception:
            logger.exception("Ошибка фонового обновления расписания.")

        if stop_event.wait(SCHEDULE_REFRESH_INTERVAL_SECONDS):
            break

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = threading.Event()
    refresher_thread = threading.Thread(
        target=schedule_refresher,
        args=(stop_event,),
        name="schedule-refresher",
        daemon=True,
    )
    refresher_thread.start()
    logger.info("Фоновый поток обновления расписаний запущен (интервал 15 минут).")

    yield

    stop_event.set()
    refresher_thread.join(timeout=5)

# --- ИНИЦИАЛИЗАЦИЯ APP ---

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API ЭНДПОИНТЫ ---

@app.get("/health")
async def health_check():
    return {"status": "ok"}


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
    request: Request,
    init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
    browser_test: str = Header(default="", alias="X-Browser-Test-Mode"),
) -> dict:
    if is_local_browser_test(request, browser_test):
        user = {"id": 0, "first_name": "Локальный тест"}
        record_activity(user["id"])
        return user
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
        record_activity(user["id"])
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
    request: Request,
    user: dict = Depends(require_active_user),
    browser_test: str = Header(default="", alias="X-Browser-Test-Mode"),
) -> dict:
    if is_local_browser_test(request, browser_test):
        return user
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
            _admin_user_record(user, blocked_ids)
            for user in users
        ]
    }


def _admin_user_record(user: dict, blocked_ids: set[int]) -> dict:
    user_id = int(user["telegram_id"])
    last_activity = get_latest_activity(user_id, user.get("last_seen_at"))
    return {
        "telegram_id": user_id,
        "display_name": user.get("display_name"),
        "first_name": user.get("first_name"),
        "username": user.get("username"),
        "created_at": user.get("created_at"),
        "channel_vote": user.get("channel_vote"),
        "channel_vote_at": user.get("channel_vote_at"),
        "last_seen_at": last_activity.isoformat() if last_activity else None,
        "is_online": (
            (datetime.now(timezone.utc) - last_activity).total_seconds()
            <= ACTIVE_USER_TIMEOUT_SECONDS
            if last_activity
            else False
        ),
        "is_blocked": user_id in blocked_ids,
    }


def _admin_activity_record(record: dict) -> dict:
    user_id = int(record["telegram_id"])
    latest = get_latest_activity(user_id, record.get("last_seen_at"))
    is_online = bool(
        latest
        and (datetime.now(timezone.utc) - latest).total_seconds()
        <= ACTIVE_USER_TIMEOUT_SECONDS
    )
    return {
        "telegram_id": user_id,
        "last_seen_at": latest.isoformat() if latest else None,
        "channel_vote": record.get("channel_vote"),
        "is_online": is_online,
    }


@app.get("/api/admin/users/activity")
def get_user_activity(user: dict = Depends(require_admin_user)):
    try:
        users = get_all_users()
    except UserStoreError as exc:
        logger.exception("Не удалось прочитать активность пользователей.")
        raise HTTPException(
            status_code=500,
            detail="Не удалось загрузить активность пользователей.",
        ) from exc
    return {
        "users": [_admin_activity_record(record) for record in users]
    }


@app.post("/api/activity")
def update_activity(
    request: Request,
    user: dict = Depends(require_active_user),
    browser_test: str = Header(default="", alias="X-Browser-Test-Mode"),
):
    if is_local_browser_test(request, browser_test):
        timestamp = record_activity(user["id"])
        return {
            "last_seen_at": timestamp.isoformat(),
            "last_schedule_updated": factory.last_updated_at,
        }
    try:
        timestamp = update_user_activity(user["id"])
    except UserStoreError as exc:
        logger.exception("Не удалось обновить время активности пользователя %s.", user["id"])
        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить время последней активности.",
        ) from exc
    return {
        "last_seen_at": timestamp,
        "last_schedule_updated": factory.last_updated_at,
    }


@app.post("/api/channel-vote")
def submit_channel_vote(
    payload: ChannelVoteRequest,
    user: dict = Depends(require_active_user),
):
    if user["id"] == 0:
        return {"vote": payload.vote}
    try:
        saved = save_user_vote(user["id"], payload.vote)
    except UserStoreError as exc:
        logger.exception("Не удалось сохранить голос пользователя %s.", user["id"])
        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить голос. Попробуйте ещё раз.",
        ) from exc
    if not saved:
        raise HTTPException(status_code=409, detail="Вы уже проголосовали.")
    return {"vote": payload.vote}


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
    return {"faculties": factory.get_faculties()}

@app.get("/api/faculties/{fac}/groups")
async def get_groups(fac: str, user: dict = Depends(require_active_user)):
    try:
        groups = await asyncio.to_thread(factory.get_groups, fac)
    except (requests.RequestException, ValueError) as exc:
        logger.exception("Не удалось загрузить группы факультета %s.", fac)
        raise HTTPException(
            503,
            "Источник расписаний временно недоступен.",
        ) from exc
    if groups is None:
        raise HTTPException(404, "Факультет не найден")
    if not groups:
        raise HTTPException(503, "Список групп ещё загружается")
    return {"groups": groups}

@app.get("/api/faculties/{fac}/groups/{group}/subgroups")
async def get_subgroups(
    fac: str,
    group: str,
    user: dict = Depends(require_active_user),
):
    try:
        subgroups = await asyncio.to_thread(factory.get_subgroups, fac, group)
    except (requests.RequestException, ValueError) as exc:
        logger.exception("Не удалось загрузить подгруппы %s факультета %s.", group, fac)
        raise HTTPException(
            503,
            "Источник расписаний временно недоступен.",
        ) from exc
    if subgroups is None:
        raise HTTPException(404, "Группа не найдена")
    return {"subgroups": subgroups}

@app.get("/api/schedule/{group}")
async def get_sched(
    group: str,
    faculty: str | None = None,
    subgroup_id: str | None = Query(default=None, alias="subgroup"),
    user: dict = Depends(require_active_user),
):
    try:
        sched = await asyncio.to_thread(
            factory.get_schedule,
            group,
            faculty,
            None if subgroup_id in (None, "all") else subgroup_id,
        )
    except (requests.RequestException, ValueError) as exc:
        logger.exception("Не удалось загрузить расписание группы %s.", group)
        raise HTTPException(
            503,
            "Источник расписаний временно недоступен.",
        ) from exc
    if not sched: raise HTTPException(404)
    return {
        "schedule": sched,
        "last_updated": factory.last_updated_at,
    }


@app.get("/api/rooms/locations")
async def get_room_locations(user: dict = Depends(require_active_user)):
    return {"locations": await asyncio.to_thread(factory.get_room_locations)}


@app.get("/api/rooms")
async def search_rooms(
    location: str = Query(min_length=1),
    room: str = Query(default=""),
    user: dict = Depends(require_active_user),
):
    try:
        sched = await asyncio.to_thread(factory.search_room, room, location)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"schedule": sched}

# НОВЫЙ ЭНДПОИНТ: ПОИСК ПО ПРЕПОДАВАТЕЛЮ
@app.get("/api/teacher/{name}")
async def search_teacher(name: str, user: dict = Depends(require_active_user)):
    query = name.lower().strip()
    if len(query) < 3:
        raise HTTPException(400, "Минимум 3 символа для поиска")

    teacher_schedule = {}
    
    # Проходим по всем факультетам и их группам в памяти
    for group, sched in factory.iter_schedules():
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