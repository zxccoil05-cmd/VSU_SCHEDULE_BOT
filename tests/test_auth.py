import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch

from bot import auth


BOT_TOKEN = "test-bot-token"


def signed_init_data(user: dict, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
    ).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


class TelegramAuthTests(unittest.TestCase):
    def test_verifies_signed_telegram_user(self):
        user = {"id": 12345, "first_name": "Тест", "username": "test_user"}

        self.assertEqual(
            auth.verify_telegram_init_data(signed_init_data(user), BOT_TOKEN),
            user,
        )

    def test_rejects_tampered_init_data(self):
        init_data = signed_init_data({"id": 12345, "first_name": "Тест"})
        tampered = init_data.replace("12345", "54321")

        with self.assertRaises(auth.TelegramInitDataError):
            auth.verify_telegram_init_data(tampered, BOT_TOKEN)

    def test_rejects_non_hex_hash(self):
        init_data = signed_init_data({"id": 12345})
        tampered = init_data.rsplit("=", 1)[0] + "=" + ("ж" * 64)

        with self.assertRaises(auth.TelegramInitDataError):
            auth.verify_telegram_init_data(tampered, BOT_TOKEN)

    def test_rejects_expired_init_data(self):
        expired = signed_init_data(
            {"id": 12345}, auth_date=int(time.time()) - auth.MAX_INIT_DATA_AGE_SECONDS - 1
        )

        with self.assertRaises(auth.TelegramInitDataError):
            auth.verify_telegram_init_data(expired, BOT_TOKEN)

    def test_blacklist_ignores_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            blacklist_file = Path(directory) / "blacklist.txt"
            blacklist_file.write_text("# blocked\n\n12345\n", encoding="utf-8")
            with patch.object(auth, "BLACKLIST_FILE", blacklist_file):
                self.assertTrue(auth.is_user_blacklisted(12345))
                self.assertFalse(auth.is_user_blacklisted(54321))

    def test_adds_and_removes_user_from_blacklist_preserving_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            blacklist_file = Path(directory) / "blacklist.txt"
            blacklist_file.write_text("# keep this comment\n\n12345\n", encoding="utf-8")
            with patch.object(auth, "BLACKLIST_FILE", blacklist_file):
                self.assertTrue(auth.set_user_blacklisted(54321, True))
                self.assertEqual(auth.get_blacklisted_user_ids(), {12345, 54321})
                self.assertFalse(auth.set_user_blacklisted(12345, False))
                self.assertEqual(auth.get_blacklisted_user_ids(), {54321})

            contents = blacklist_file.read_text(encoding="utf-8")
            self.assertIn("# keep this comment", contents)
            self.assertNotIn("12345", contents)

    def test_rejects_non_positive_blacklist_id(self):
        with self.assertRaises(ValueError):
            auth.set_user_blacklisted(0, True)

    def test_admin_file_ignores_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            admins_file = Path(directory) / "admins.txt"
            admins_file.write_text("# admins\n\n12345\n", encoding="utf-8")
            with patch.object(auth, "ADMINS_FILE", admins_file):
                self.assertTrue(auth.is_user_admin(12345))
                self.assertFalse(auth.is_user_admin(54321))

    def test_saves_user_and_preserves_first_seen(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / "users.json"
            user = {"id": 12345, "first_name": "Тест", "username": "test_user"}
            with patch.object(auth, "USERS_FILE", users_file):
                first_save = auth.save_user(user)
                second_save = auth.save_user({**user, "first_name": "Новое имя"})
                stored = json.loads(users_file.read_text(encoding="utf-8"))

            self.assertEqual(first_save["created_at"], second_save["created_at"])
            self.assertEqual(stored["12345"]["first_name"], "Новое имя")
            self.assertEqual(stored["12345"]["username"], "test_user")

    def test_persists_one_channel_vote_and_preserves_it_on_login(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / "users.json"
            user = {"id": 12345, "first_name": "Тест"}
            with patch.object(auth, "USERS_FILE", users_file):
                auth.save_user(user)
                self.assertTrue(auth.save_user_vote(12345, "yes"))
                self.assertFalse(auth.save_user_vote(12345, "no"))
                saved = auth.save_user({**user, "first_name": "Обновлённое имя"})
                stored = json.loads(users_file.read_text(encoding="utf-8"))["12345"]

            self.assertEqual(saved["channel_vote"], "yes")
            self.assertEqual(stored["channel_vote"], "yes")
            self.assertEqual(stored["channel_vote_at"], saved["channel_vote_at"])

    def test_updates_persisted_user_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / "users.json"
            with patch.object(auth, "USERS_FILE", users_file):
                auth.save_user({"id": 12345, "first_name": "Тест"})
                timestamp = auth.update_user_activity(12345)
                stored = json.loads(users_file.read_text(encoding="utf-8"))["12345"]

            self.assertEqual(stored["last_seen_at"], timestamp)
            self.assertIsNotNone(auth.datetime.fromisoformat(timestamp).tzinfo)

    def test_get_all_users_returns_newest_first_without_modifying_data(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / "users.json"
            stored_users = {
                "123": {"telegram_id": 123, "created_at": "2026-01-01T00:00:00+00:00"},
                "456": {"telegram_id": 456, "created_at": "2026-02-01T00:00:00+00:00"},
            }
            users_file.write_text(json.dumps(stored_users), encoding="utf-8")
            with patch.object(auth, "USERS_FILE", users_file):
                users = auth.get_all_users()

            self.assertEqual([user["telegram_id"] for user in users], [456, 123])
            self.assertEqual(
                json.loads(users_file.read_text(encoding="utf-8")),
                stored_users,
            )


if __name__ == "__main__":
    unittest.main()
