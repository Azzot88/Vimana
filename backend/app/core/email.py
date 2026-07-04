import smtplib
from email.mime.text import MIMEText

from app.core.config import settings


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USER or not to:
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_USER, [to], msg.as_string())
