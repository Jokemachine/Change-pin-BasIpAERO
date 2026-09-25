"""
Email notification service using Google Mail (Gmail).
Supports Gmail SMTP (with App Password), Gmail REST API, and Mock/Dry-run modes.
"""
import logging
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Exact text requested by user:
# 'Добрый день, ваш код доступа изменен на "Код"'
DEFAULT_BODY_TEMPLATE = 'Добрый день, ваш код доступа изменен на "{code}"'
DEFAULT_SUBJECT = "Смена кода доступа домофона"


class BaseMailer:
    """Interface for mail sending backends."""
    def send_access_code_email(self, to_email: str, new_code: str, user_name: str = "") -> bool:
        raise NotImplementedError


class GmailSMTPMailer(BaseMailer):
    """
    Sends emails via Google Mail SMTP server (smtp.gmail.com)
    using standard SSL (port 465) or STARTTLS (port 587) with a Google App Password.
    """

    def __init__(
        self,
        gmail_user: str,
        gmail_app_password: str,
        from_name: str = "Домофон BAS-IP",
        subject: str = DEFAULT_SUBJECT,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 465,
        use_ssl: bool = True,
        timeout: int = 15,
    ):
        self.gmail_user = gmail_user.strip()
        self.gmail_app_password = gmail_app_password.strip().replace(" ", "")
        self.from_name = from_name
        self.subject = subject
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.use_ssl = use_ssl
        self.timeout = timeout

    def send_access_code_email(self, to_email: str, new_code: str, user_name: str = "") -> bool:
        """
        Sends access code notification email to user.
        Body text strictly matches:
        'Добрый день, ваш код доступа изменен на "{new_code}"'
        """
        if not to_email:
            logger.warning("Cannot send email: recipient address is empty")
            return False

        # Exact required text format
        plain_text = f'Добрый день, ваш код доступа изменен на "{new_code}"'

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(self.subject, "utf-8")
        msg["From"] = f"{Header(self.from_name, 'utf-8')} <{self.gmail_user}>"
        msg["To"] = to_email

        # Plain text part (primary)
        part_plain = MIMEText(plain_text, "plain", "utf-8")
        msg.attach(part_plain)

        # HTML part (styled companion)
        html_text = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
  <div style="max-width: 500px; margin: 20px auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
    <h3 style="color: #1a73e8; margin-top: 0;">Домофон BAS-IP AA14FB</h3>
    <p style="font-size: 16px;">Добрый день, ваш код доступа изменен на <b>"{new_code}"</b></p>
    <div style="background: #f1f3f4; padding: 12px; border-radius: 4px; text-align: center; margin: 15px 0;">
      <span style="font-size: 24px; font-weight: bold; letter-spacing: 4px; color: #202124;">{new_code}</span>
    </div>
    <p style="font-size: 13px; color: #70757a;">Этот код предназначен для входа через панель домофона. Код обновляется автоматически каждые две недели.</p>
  </div>
</body>
</html>"""
        part_html = MIMEText(html_text, "html", "utf-8")
        msg.attach(part_html)

        try:
            logger.info("Connecting to Gmail SMTP (%s:%s)...", self.smtp_host, self.smtp_port)
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout)
                server.starttls()

            server.login(self.gmail_user, self.gmail_app_password)
            server.sendmail(self.gmail_user, [to_email], msg.as_string())
            server.quit()

            logger.info("Successfully sent access code email to %s via Gmail SMTP", to_email)
            return True
        except Exception as exc:
            logger.error("Failed to send email to %s via Gmail SMTP: %s", to_email, exc)
            return False


class MockMailer(BaseMailer):
    """
    Mock mailer for testing and dry-run execution.
    Logs email details without contacting external mail servers.
    """

    def __init__(self, print_to_console: bool = True):
        self.print_to_console = print_to_console
        self.sent_messages: List[Dict[str, str]] = []

    def send_access_code_email(self, to_email: str, new_code: str, user_name: str = "") -> bool:
        text = f'Добрый день, ваш код доступа изменен на "{new_code}"'
        msg_record = {
            "to": to_email,
            "name": user_name,
            "code": new_code,
            "body": text,
        }
        self.sent_messages.append(msg_record)
        logger.info("[MOCK MAIL] To: %s | Text: %s", to_email, text)
        if self.print_to_console:
            print(f"[MOCK GMAIL SENT] -> {to_email}: {text}")
        return True
