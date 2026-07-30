import smtplib
import ssl
from email.mime.text import MIMEText

from app.core.config import settings


def _connect() -> smtplib.SMTP:
    """Open a connection, letting the port decide how TLS starts.

    465 speaks TLS from the first byte; 587 opens in clear text and upgrades
    with STARTTLS. Sending the wrong one fails during the handshake with an
    error that reads like a broken certificate, so the port decides rather than
    yet another setting nobody would keep in sync with it.

    The context is passed explicitly because smtplib's default has moved
    between verifying the certificate and not, depending on the Python version.
    This link carries the mailbox password — inheriting an unverified TLS
    session from a version-dependent default is not a choice worth making by
    accident. Consequence to keep in mind: `SMTP_HOST` must be the name on the
    certificate, so a bare IP address will now be rejected.
    """
    context = ssl.create_default_context()
    if settings.SMTP_PORT == 465:
        return smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context)
    smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
    smtp.starttls(context=context)
    return smtp


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USER or not to:
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    with _connect() as smtp:
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_USER, [to], msg.as_string())
