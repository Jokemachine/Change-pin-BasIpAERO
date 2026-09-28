"""
Tests for email sending service.
"""
from unittest.mock import MagicMock, patch
from google_services.mailer import MockMailer, GmailSMTPMailer, DEFAULT_BODY_TEMPLATE


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


@patch("smtplib.SMTP_SSL")
def test_gmail_smtp_mailer_multiple_recipients(mock_smtp_cls):
    import email
    mock_server = MagicMock()
    mock_smtp_cls.return_value = mock_server

    mailer = GmailSMTPMailer(
        gmail_user="admin@gmail.com",
        gmail_app_password="secretpassword",
        use_ssl=True,
    )

    # Test comma-separated emails
    to_input = "Mir-ned39@mail.ru, dmolokanov@mail.ru"
    ok = mailer.send_access_code_email(to_input, "765432", user_name="Молоканов")
    assert ok is True

    # Ensure sendmail was called with list of split recipient emails
    mock_server.sendmail.assert_called_once()
    sender, recipients, msg_str = mock_server.sendmail.call_args[0]
    assert sender == "admin@gmail.com"
    assert recipients == ["Mir-ned39@mail.ru", "dmolokanov@mail.ru"]

    parsed = email.message_from_string(msg_str)
    assert parsed["To"] == "Mir-ned39@mail.ru, dmolokanov@mail.ru"
    # Find plain text part and decode
    payload = None
    for part in parsed.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True).decode("utf-8")
            break
    assert payload == 'Добрый день, ваш код доступа изменен на "765432"'


@patch("smtplib.SMTP_SSL")
def test_gmail_smtp_mailer_semicolon_recipients(mock_smtp_cls):
    mock_server = MagicMock()
    mock_smtp_cls.return_value = mock_server

    mailer = GmailSMTPMailer(
        gmail_user="admin@gmail.com",
        gmail_app_password="secretpassword",
        use_ssl=True,
    )

    to_input = "user1@example.com;  user2@example.org "
    ok = mailer.send_access_code_email(to_input, "123456")
    assert ok is True

    sender, recipients, msg_str = mock_server.sendmail.call_args[0]
    assert recipients == ["user1@example.com", "user2@example.org"]
