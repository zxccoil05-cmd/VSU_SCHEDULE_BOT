import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl


PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERS_FILE = Path(os.getenv("USERS_FILE", str(PROJECT_ROOT / "users.json")))
BLACKLIST_FILE = Path(os.getenv("BLACKLIST_FILE", str(PROJECT_ROOT / "blacklist.txt")))
ADMINS_FILE = Path(os.getenv("ADMINS_FILE", str(PROJECT_ROOT / "admins.txt")))
MAX_INIT_DATA_AGE_SECONDS = 86400
_users_lock = threading.Lock()
_blacklist_lock = threading.Lock()


class TelegramInitDataError(ValueError):
    pass


class UserStoreError(RuntimeError):
    pass


class BlacklistError(RuntimeError):
    pass


class AdminsFileError(RuntimeError):
    pass


def _read_users_locked() -> dict[str, dict]:
    try:
        users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        users = {}
    except (OSError, json.JSONDecodeError) as exc:
        raise UserStoreError("Не удалось прочитать users.json.") from exc

    if not isinstance(users, dict) or any(
        not isinstance(record, dict) for record in users.values()
    ):
        raise UserStoreError("Некорректный формат users.json.")
    return users


def _write_users_locked(users: dict[str, dict]) -> None:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=USERS_FILE.parent,
            prefix=".users-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(users, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
        os.replace(temp_path, USERS_FILE)
    except OSError as exc:
        raise UserStoreError("Не удалось сохранить users.json.") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    if not init_data or len(init_data) > 8192:
        raise TelegramInitDataError("Некорректные данные Telegram.")

    try:
        pairs = parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=20,
        )
    except ValueError as exc:
        raise TelegramInitDataError("Некорректные данные Telegram.") from exc

    data = dict(pairs)
    if len(data) != len(pairs):
        raise TelegramInitDataError("Некорректные данные Telegram.")

    received_hash = data.get("hash", "")
    if len(received_hash) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in received_hash
    ):
        raise TelegramInitDataError("Не удалось подтвердить аккаунт Telegram.")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data.items()) if key != "hash"
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramInitDataError("Не удалось подтвердить аккаунт Telegram.")

    try:
        auth_date = int(data["auth_date"])
        user = json.loads(data["user"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramInitDataError("В данных Telegram отсутствует профиль.") from exc

    now = int(time.time())
    if auth_date > now + 30 or now - auth_date > MAX_INIT_DATA_AGE_SECONDS:
        raise TelegramInitDataError("Срок проверки Telegram истёк. Перезапустите приложение.")
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise TelegramInitDataError("В данных Telegram отсутствует ID аккаунта.")

    return user


def is_user_blacklisted(user_id: int) -> bool:
    return user_id in get_blacklisted_user_ids()


def get_blacklisted_user_ids() -> set[int]:
    try:
        lines = BLACKLIST_FILE.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise BlacklistError("Не удалось прочитать blacklist.txt.") from exc

    blocked_ids = set()
    for line_number, line in enumerate(lines, start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if not value.isdecimal():
            raise BlacklistError(
                f"Некорректный Telegram ID в blacklist.txt, строка {line_number}."
            )
        blocked_ids.add(int(value))

    return blocked_ids


def set_user_blacklisted(user_id: int, blocked: bool) -> bool:
    if user_id <= 0:
        raise ValueError("Telegram ID должен быть положительным числом.")

    with _blacklist_lock:
        try:
            lines = BLACKLIST_FILE.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            lines = []
        except OSError as exc:
            raise BlacklistError("Не удалось прочитать blacklist.txt.") from exc

        blocked_ids = set()
        for line_number, line in enumerate(lines, start=1):
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if not value.isdecimal():
                raise BlacklistError(
                    f"Некорректный Telegram ID в blacklist.txt, строка {line_number}."
                )
            blocked_ids.add(int(value))

        if blocked:
            blocked_ids.add(user_id)
        else:
            blocked_ids.discard(user_id)

        comments = [
            line for line in lines if not line.strip() or line.lstrip().startswith("#")
        ]
        updated_lines = comments + [str(blocked_id) for blocked_id in sorted(blocked_ids)]
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=BLACKLIST_FILE.parent,
                prefix=".blacklist-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write("\n".join(updated_lines) + "\n")
            os.replace(temp_path, BLACKLIST_FILE)
        except OSError as exc:
            raise BlacklistError("Не удалось обновить blacklist.txt.") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    return blocked


def is_user_admin(user_id: int) -> bool:
    try:
        lines = ADMINS_FILE.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise AdminsFileError("Не удалось прочитать admins.txt.") from exc

    admin_ids = set()
    for line_number, line in enumerate(lines, start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if not value.isdecimal():
            raise AdminsFileError(
                f"Некорректный Telegram ID в admins.txt, строка {line_number}."
            )
        admin_ids.add(int(value))

    return user_id in admin_ids


def save_user(user: dict) -> dict:
    user_id = str(user["id"])
    now = datetime.now(timezone.utc).isoformat()

    with _users_lock:
        users = _read_users_locked()
        previous = users.get(user_id, {})
        first_name = user.get("first_name", "")
        last_name = user.get("last_name", "")
        users[user_id] = {
            "telegram_id": int(user_id),
            "username": user.get("username"),
            "first_name": first_name,
            "last_name": last_name,
            "display_name": " ".join(part for part in (first_name, last_name) if part),
            "created_at": previous.get("created_at", now),
            "last_seen_at": now,
            "channel_vote": previous.get("channel_vote"),
            "channel_vote_at": previous.get("channel_vote_at"),
        }
        _write_users_locked(users)

    return users[user_id]


def update_user_activity(user_id: int) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with _users_lock:
        users = _read_users_locked()
        record = users.get(str(user_id))
        if record is None:
            raise UserStoreError("Пользователь не найден в users.json.")
        record["last_seen_at"] = now
        _write_users_locked(users)
    return now


def save_user_vote(user_id: int, vote: str) -> bool:
    if vote not in {"yes", "no"}:
        raise ValueError("Недопустимый вариант голосования.")
    with _users_lock:
        users = _read_users_locked()
        record = users.get(str(user_id))
        if record is None:
            raise UserStoreError("Пользователь не найден в users.json.")
        if record.get("channel_vote") in {"yes", "no"}:
            return False
        record["channel_vote"] = vote
        record["channel_vote_at"] = datetime.now(timezone.utc).isoformat()
        _write_users_locked(users)
    return True


def get_all_users() -> list[dict]:
    with _users_lock:
        users = _read_users_locked()

    return sorted(
        users.values(),
        key=lambda user: user.get("created_at", ""),
        reverse=True,
    )
