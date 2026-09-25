"""
Tests for email sending service.
"""
from google_services.mailer import MockMailer, DEFAULT_BODY_TEMPLATE


def test_mock_mailer_exact_format():
    mailer = MockMailer(print_to_console=False)
    pin = "482019"
    ok = mailer.send_access_code_email("client@example.com", pin, user_name="Иван")
    assert ok is True
    assert len(mailer.sent_messages) == 1

    msg = mailer.sent_messages[0]
    assert msg["to"] == "client@example.com"
    assert msg["code"] == pin
    # Verify exact user phrase: 'Добрый день, ваш код доступа изменен на "Код"'
    assert msg["body"] == f'Добрый день, ваш код доступа изменен на "{pin}"'
