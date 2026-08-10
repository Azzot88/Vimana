import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import settings

# The name shown next to the address in a mail client. A brand constant rather
# than configuration: it is the same in every environment, and an env var would
# be one more thing to keep in sync across two servers for no gain.
FROM_DISPLAY_NAME = "Vimana — Sacred Logistics"


@dataclass(frozen=True)
class Circuit:
    """One SMTP destination. Two exist and they never share a value.

    `live()` is the mailbox real people are written from. `preview()` is a
    catcher (Mailpit) used by the admin page's test send. Keeping them as two
    objects rather than one set of settings with a toggle is the whole point:
    a toggle is one edit away from swallowing production mail silently.
    """

    host: str
    port: int
    user: str
    password: str

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user)


def live() -> Circuit:
    return Circuit(
        settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER, settings.SMTP_PASSWORD
    )


def preview() -> Circuit:
    return Circuit(
        settings.PREVIEW_SMTP_HOST,
        settings.PREVIEW_SMTP_PORT,
        settings.PREVIEW_SMTP_USER,
        settings.PREVIEW_SMTP_PASSWORD,
    )


def _connect(circuit: Circuit) -> smtplib.SMTP:
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
    if circuit.port == 465:
        context = ssl.create_default_context()
        return smtplib.SMTP_SSL(circuit.host, circuit.port, context=context)
    smtp = smtplib.SMTP(circuit.host, circuit.port)
    # EHLO first: `has_extn` reads the feature list the greeting fills in, and
    # without it the check below is always False.
    smtp.ehlo()
    # A local catcher speaks plain SMTP and has no certificate to verify.
    # STARTTLS is attempted only where the server offers it, so the live path
    # (587) still upgrades and the preview path (1025) does not fail trying.
    if smtp.has_extn("starttls"):
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
    return smtp


def send_email(
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    circuit: Circuit | None = None,
) -> bool:
    """Send a message. Returns True only if it was handed to the SMTP server.

    The boolean exists because the silent `return` below is otherwise
    indistinguishable from success at the call site — and a caller that records
    "notified" on the strength of that is writing down something that did not
    happen. Telegram and WhatsApp went a whole release doing exactly this
    (TECHSTATE §1, T1.7): unconfigured transport, silent exit, green status.

    Callers that only fire and forget may ignore the result. Callers that
    persist a "sent" mark must not.
    """
    wire = circuit or live()
    if not wire.configured or not to:
        return False
    # Belt and braces behind `is_valid_email`. Addresses predating that check
    # are already in the database, and one of them would otherwise take down
    # whichever task tried to write to it — `sendmail` encodes the envelope as
    # ASCII and raises. Returning False keeps the failure in the shape every
    # caller already handles, instead of an exception from the transport.
    if not to.isascii():
        return False
    if html:
        # `multipart/alternative`, plain part first: the order is the standard's
        # way of saying "last is richest", and a client picks the last part it
        # can render. Reversing it is how a modern inbox ends up showing raw
        # markup.
        #
        # The text part is never dropped, even though every mainstream client
        # renders HTML. Filters read it, some clients are configured to prefer
        # it, and an HTML-only message loses reputation points before it is
        # read by anyone (T_UX.9; the same lesson as the missing `Date` header).
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    # `formataddr` RFC 2047-encodes the name — it contains an em dash, and raw
    # UTF-8 in a header gets messages dropped by some receivers. The envelope
    # sender below stays the bare address: the display name is decoration for
    # the recipient, not part of the address mail is routed by.
    msg["From"] = formataddr((FROM_DISPLAY_NAME, wire.user))
    msg["To"] = to
    # `Date` and `Message-ID` are required by RFC 5322 and nobody else adds
    # them: Python does not, and Postfix leaves submitted mail alone by
    # default. Spam filters score their absence heavily — the first message
    # this code sent picked up three points from its own server before ever
    # reaching a recipient's. No DNS record can compensate for a malformed
    # message.
    msg["Date"] = formatdate(localtime=True)
    _, at, domain = wire.user.rpartition("@")
    msg["Message-ID"] = make_msgid(domain=domain if at else None)
    with _connect(wire) as smtp:
        smtp.ehlo()
        # A catcher accepts anything and offers no AUTH; logging in there fails
        # with a protocol error rather than a credentials one.
        if smtp.has_extn("auth"):
            smtp.login(wire.user, wire.password)
        smtp.sendmail(wire.user, [to], msg.as_string())
    return True
