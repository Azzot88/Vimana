import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings

log = logging.getLogger(__name__)


def sender_address() -> str:
    """The address the recipient sees, and the envelope sender.

    Both are the same value on purpose. Splitting them is what SES does by
    default — envelope from `amazonses.com`, header from our domain — and it
    costs SPF alignment: the domain SPF vouches for stops matching the domain
    in `From`. DKIM then carries DMARC alone. Sending both as our own address
    keeps that fallback intact when the relay allows it.
    """
    return settings.SMTP_FROM or settings.SMTP_USER


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USER or not to:
        # Not a failure: a dev box with no SMTP configured still has to run.
        # Logged rather than silent — an unconfigured relay in production looks
        # exactly like a working one until someone notices no mail arrives.
        log.info("email skipped, SMTP not configured (to=%s, subject=%s)", to, subject)
        return

    frm = sender_address()
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    # `formataddr` RFC 2047-encodes a non-ASCII display name; a raw f-string
    # would put raw UTF-8 in a header and some receivers drop the message.
    msg["From"] = formataddr((settings.SMTP_FROM_NAME, frm)) if settings.SMTP_FROM_NAME else frm
    msg["To"] = to
    if settings.SMTP_REPLY_TO:
        msg["Reply-To"] = settings.SMTP_REPLY_TO

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(frm, [to], msg.as_string())
