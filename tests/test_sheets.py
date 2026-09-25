"""
Tests for sheets backend and local CSV handler.
"""
import os
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime
from google_services.sheets import (
    LocalCSVSheetsBackend,
    GoogleAppsScriptBackend,
    AppSheetBackend,
    DEFAULT_HEADERS,
)


def test_local_csv_read_write():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        temp_path = tf.name

    try:
        backend = LocalCSVSheetsBackend(temp_path)
        users = backend.get_users()
        assert len(users) >= 2

        # Check first user
        user = users[0]
        old_code = user.current_code
        new_code = "999888"

        # Update code
        now = datetime(2026, 9, 23, 14, 0, 0)
        success = backend.update_user_code(user, new_code, rotation_time=now, status="Тест пройден")
        assert success is True

        # Re-read file to ensure persistence
        backend2 = LocalCSVSheetsBackend(temp_path)
        users2 = backend2.get_users()
        assert users2[0].current_code == new_code
        assert users2[0].status == "Тест пройден"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_google_apps_script_backend():
    gas = GoogleAppsScriptBackend("https://script.google.com/macros/s/TEST/exec", api_key="secret123")

    fake_get_response = MagicMock()
    fake_get_response.status_code = 200
    fake_get_response.json.return_value = {
        "success": True,
        "users": [
            {
                "row_index": 2,
                "id": "101",
                "name": "Иванов И.И.",
                "email": "ivanov@test.com",
                "apartment": "12",
                "code": "123456",
                "auto_rotate": "Да",
                "last_rotated": "2026-09-01 10:00:00",
                "interval_days": 14,
                "status": "Активен",
            }
        ],
    }

    fake_post_response = MagicMock()
    fake_post_response.status_code = 200
    fake_post_response.json.return_value = {"success": True, "code": "654321"}

    with patch("requests.get", return_value=fake_get_response) as mock_get:
        users = gas.get_users()
        assert len(users) == 1
        assert users[0].name == "Иванов И.И."
        assert users[0].current_code == "123456"
        mock_get.assert_called_once()

    with patch("requests.post", return_value=fake_post_response) as mock_post:
        user = users[0]
        ok = gas.update_user_code(user, "654321")
        assert ok is True
        assert user.current_code == "654321"
        mock_post.assert_called_once()


def test_appsheet_backend():
    appsheet = AppSheetBackend(app_id="app-12345", access_key="key-abc", table_name="Коды доступа")

    fake_find_resp = MagicMock()
    fake_find_resp.status_code = 200
    fake_find_resp.json.return_value = [
        {
            "ID": "101",
            "ФИО": "Петров П.П.",
            "Email": "petrov@test.com",
            "Рабочий код": "554433",
            "Автосмена": "Да",
            "Дата последней смены": "2026-09-10 10:00:00",
            "Интервал (дней)": 14,
            "Статус": "Активен",
        }
    ]

    fake_edit_resp = MagicMock()
    fake_edit_resp.status_code = 200
    fake_edit_resp.json.return_value = {"Rows": [{"ID": "101"}]}

    with patch("requests.post", return_value=fake_find_resp):
        users = appsheet.get_users()
        assert len(users) == 1
        assert users[0].name == "Петров П.П."
        assert users[0].current_code == "554433"

    with patch("requests.post", return_value=fake_edit_resp):
        user = users[0]
        ok = appsheet.update_user_code(user, "778899")
        assert ok is True
        assert user.current_code == "778899"

