import uuid as uuidlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.conftest import TEST_DATABASE_URL


@pytest.fixture
def sync_test_session(monkeypatch):
    sync_url = TEST_DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url, pool_pre_ping=True)
    maker = sessionmaker(engine, expire_on_commit=False)

    from app.tasks import notifications as notif

    monkeypatch.setattr(notif, "SyncSessionLocal", maker)
    yield maker
    engine.dispose()


@pytest.fixture
def channel_calls(monkeypatch):
    calls = {"email": [], "telegram": [], "whatsapp": []}
    from app.tasks import notifications as notif

    monkeypatch.setattr(notif, "send_email", lambda to, subj, body: calls["email"].append((to, subj, body)))
    monkeypatch.setattr(notif, "send_telegram", lambda chat, msg: calls["telegram"].append((chat, msg)))
    monkeypatch.setattr(notif, "send_whatsapp", lambda number, msg: calls["whatsapp"].append((number, msg)))
    return calls


def test_notify_deal_status_sends_email_to_both_parties(
    sync_test_session, channel_calls, seed_deal, seed_carrier, seed_sender
):
    from app.tasks.notifications import notify_deal_status

    notify_deal_status(str(seed_deal.id), "accepted")

    recipients = {c[0] for c in channel_calls["email"]}
    assert seed_carrier.email in recipients
    assert seed_sender.email in recipients


def test_notify_deal_status_no_op_for_missing_deal(sync_test_session, channel_calls):
    from app.tasks.notifications import notify_deal_status

    notify_deal_status(str(uuidlib.uuid4()), "matched")

    assert channel_calls["email"] == []
    assert channel_calls["telegram"] == []
    assert channel_calls["whatsapp"] == []


def test_notify_deal_status_uses_soft_status_label(
    sync_test_session, channel_calls, seed_deal
):
    from app.tasks.notifications import notify_deal_status

    notify_deal_status(str(seed_deal.id), "in_transit")

    assert channel_calls["email"], "expected at least one email sent"
    body = channel_calls["email"][0][2]
    assert "in_transit" not in body, "raw status must be translated to soft label"


# ── the sender's TLS handshake ────────────────────────────────────────────────
# The Mailu deployment serves 465 and not 587, so the port is not a detail we
# get to ignore: sending STARTTLS into an implicit-TLS port fails in a way that
# looks like a certificate problem and costs an evening to trace.


class _FakeSMTP:
    """Stand-in for `smtplib.SMTP`, recording how the connection was opened."""

    opened: list["_FakeSMTP"] = []

    def __init__(self, host, port, context=None):
        self.host = host
        self.port = port
        self.context = context
        self.started_tls = False
        self.login_args = None
        self.sent = []
        _FakeSMTP.opened.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, frm, to, raw):
        self.sent.append((frm, to, raw))


class _FakeSMTPSSL(_FakeSMTP):
    """Implicit TLS — a distinct class so the test can tell which was chosen."""


@pytest.fixture
def smtp_spy(monkeypatch):
    import smtplib

    from app.core.config import settings

    _FakeSMTP.opened = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTPSSL)
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.example.test")
    monkeypatch.setattr(settings, "SMTP_USER", "vimana@example.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")

    def with_port(port):
        monkeypatch.setattr(settings, "SMTP_PORT", port)
        return _FakeSMTP.opened

    return with_port


def test_port_465_uses_implicit_tls(smtp_spy):
    from app.core.email import send_email

    opened = smtp_spy(465)
    send_email("someone@example.test", "subject", "body")

    conn = opened[0]
    assert isinstance(conn, _FakeSMTPSSL), "465 must open with TLS already up"
    assert not conn.started_tls, "STARTTLS on an implicit-TLS port breaks the handshake"
    assert conn.context is not None, "TLS context must be explicit, not smtplib's default"


def test_port_587_upgrades_with_starttls(smtp_spy):
    from app.core.email import send_email

    opened = smtp_spy(587)
    send_email("someone@example.test", "subject", "body")

    conn = opened[0]
    assert type(conn) is _FakeSMTP, "587 must open in clear text first"
    assert conn.started_tls, "587 without STARTTLS would send the password unencrypted"


def test_credentials_and_envelope(smtp_spy):
    from app.core.email import send_email

    opened = smtp_spy(465)
    send_email("someone@example.test", "subject", "body")

    conn = opened[0]
    assert conn.login_args == ("vimana@example.test", "secret")
    frm, recipients, _ = conn.sent[0]
    assert frm == "vimana@example.test"
    assert recipients == ["someone@example.test"]


def test_no_connection_without_configuration(smtp_spy, monkeypatch):
    from app.core.config import settings
    from app.core.email import send_email

    opened = smtp_spy(465)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    send_email("someone@example.test", "subject", "body")

    assert opened == [], "an unconfigured host must not reach the network"
