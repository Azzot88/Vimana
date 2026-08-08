import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import settings

# The name shown next to the address in a mail client. A brand constant rather
# than configuration: it is the same in every environment, and an env var would
# be one more thing to keep in sync across two servers for no gain.
FROM_DISPLAY_NAME = "Vimana — Sacred Logistics"


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


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a message. Returns True only if it was handed to the SMTP server.

    The boolean exists because the silent `return` below is otherwise
    indistinguishable from success at the call site — and a caller that records
    "notified" on the strength of that is writing down something that did not
    happen. Telegram and WhatsApp went a whole release doing exactly this
    (TECHSTATE §1, T1.7): unconfigured transport, silent exit, green status.

    Callers that only fire and forget may ignore the result. Callers that
    persist a "sent" mark must not.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USER or not to:
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    # `formataddr` RFC 2047-encodes the name — it contains an em dash, and raw
    # UTF-8 in a header gets messages dropped by some receivers. The envelope
    # sender below stays the bare address: the display name is decoration for
    # the recipient, not part of the address mail is routed by.
    msg["From"] = formataddr((FROM_DISPLAY_NAME, settings.SMTP_USER))
    msg["To"] = to
    # `Date` and `Message-ID` are required by RFC 5322 and nobody else adds
    # them: Python does not, and Postfix leaves submitted mail alone by
    # default. Spam filters score their absence heavily — the first message
    # this code sent picked up three points from its own server before ever
    # reaching a recipient's. No DNS record can compensate for a malformed
    # message.
    msg["Date"] = formatdate(localtime=True)
    _, at, domain = settings.SMTP_USER.rpartition("@")
    msg["Message-ID"] = make_msgid(domain=domain if at else None)
    with _connect() as smtp:
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_USER, [to], msg.as_string())
    return True
