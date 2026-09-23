"""
Tests for access code rotation logic and PIN generator.
"""
from datetime import datetime, timedelta
import pytest

from basip.client import BASIPManager
from basip.mock_panel import MockBASIPServer
from basip.models import AccessCodeUser, BASIPPanelConfig
from core.config import RotationConfig
from core.rotator import PINRotator, generate_secure_pin, is_trivial_pin
from google_services.mailer import MockMailer
from google_services.sheets import BaseSheetsBackend


class InMemorySheetsBackend(BaseSheetsBackend):
    def __init__(self, users):
        self.users = users

    def get_users(self):
        return self.users

    def update_user_code(self, user, new_code, rotation_time=None, status="Updated"):
        user.current_code = new_code
        user.last_rotated = rotation_time or datetime.now()
        user.status = status
        return True


def test_pin_generation():
    # Test length
    pin6 = generate_secure_pin(length=6)
    assert len(pin6) == 6
    assert pin6.isdigit()

    pin4 = generate_secure_pin(length=4)
    assert len(pin4) == 4
    assert pin4.isdigit()

    # Test trivial detection
    assert is_trivial_pin("000000") is True
    assert is_trivial_pin("111111") is True
    assert is_trivial_pin("123456") is True
    assert is_trivial_pin("654321") is True
    assert is_trivial_pin("582914") is False

    # Test uniqueness against existing codes
    existing = {"111222", "333444"}
    new_pin = generate_secure_pin(length=6, existing_codes=existing)
    assert new_pin not in existing


def test_user_is_due_for_rotation():
    now = datetime(2026, 9, 23, 12, 0, 0)

    # 1. auto_rotate is False -> never due
    u1 = AccessCodeUser(
        row_index=2,
        user_id="1",
        name="User 1",
        email="u1@test.com",
        current_code="123456",
        auto_rotate=False,
        last_rotated=now - timedelta(days=30),
    )
    assert u1.is_due_for_rotation(now) is False

    # 2. No current code -> due immediately
    u2 = AccessCodeUser(
        row_index=3,
        user_id="2",
        name="User 2",
        email="u2@test.com",
        current_code="",
        auto_rotate=True,
    )
    assert u2.is_due_for_rotation(now) is True

    # 3. Rotated 15 days ago -> due (interval is 14 days)
    u3 = AccessCodeUser(
        row_index=4,
        user_id="3",
        name="User 3",
        email="u3@test.com",
        current_code="123456",
        auto_rotate=True,
        last_rotated=now - timedelta(days=15),
        interval_days=14,
    )
    assert u3.is_due_for_rotation(now) is True

    # 4. Rotated 10 days ago -> NOT due
    u4 = AccessCodeUser(
        row_index=5,
        user_id="4",
        name="User 4",
        email="u4@test.com",
        current_code="123456",
        auto_rotate=True,
        last_rotated=now - timedelta(days=10),
        interval_days=14,
    )
    assert u4.is_due_for_rotation(now) is False


def test_rotation_flow():
    server = MockBASIPServer(host="127.0.0.1", port=18082)
    server.start()

    try:
        panel_cfg = BASIPPanelConfig(host="127.0.0.1", port=18082, username="admin", password="123456")
        manager = BASIPManager([panel_cfg])
        mailer = MockMailer(print_to_console=False)

        now = datetime.now()
        users = [
            # Due for rotation (> 14 days)
            AccessCodeUser(
                row_index=2,
                user_id="user_1",
                name="Иванов Иван",
                email="ivanov@example.com",
                current_code="111222",
                auto_rotate=True,
                last_rotated=now - timedelta(days=16),
                interval_days=14,
            ),
            # Not due (< 14 days)
            AccessCodeUser(
                row_index=3,
                user_id="user_2",
                name="Петров Петр",
                email="petrov@example.com",
                current_code="333444",
                auto_rotate=True,
                last_rotated=now - timedelta(days=5),
                interval_days=14,
            ),
        ]

        backend = InMemorySheetsBackend(users)
        rotator = PINRotator(
            basip_manager=manager,
            sheets_backend=backend,
            mailer=mailer,
            config=RotationConfig(interval_days=14, code_length=6, dry_run=False),
        )

        report = rotator.rotate_all_due_users(force=False)
        assert report.total_users_checked == 2
        assert report.rotated_count == 1
        assert report.skipped_count == 1
        assert report.failed_count == 0

        # Verify user 1 code changed
        assert users[0].current_code != "111222"
        # Verify user 2 code remained the same
        assert users[1].current_code == "333444"

        # Verify email was sent to user 1 with exact text
        assert len(mailer.sent_messages) == 1
        sent = mailer.sent_messages[0]
        assert sent["to"] == "ivanov@example.com"
        assert sent["code"] == users[0].current_code
        expected_phrase = f'Добрый день, ваш код доступа изменен на "{users[0].current_code}"'
        assert sent["body"] == expected_phrase
    finally:
        server.stop()
