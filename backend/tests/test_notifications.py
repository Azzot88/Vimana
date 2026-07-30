import uuid as uuidlib
from email import message_from_string

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


# ── the sender itself ─────────────────────────────────────────────────────────
# `core.email.send_email` had no tests at all while it was three lines and the
# `From` header was hard-wired to `SMTP_USER`. It stopped being obvious once the
# visible sender became configurable, and the header's domain is what DMARC is
# judged on — a silent regression there means mail lands in spam, not that it
# fails loudly.


class _FakeSMTP:
    """Stand-in for `smtplib.SMTP`, recording the envelope and raw message."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sent = []
        self.logged_in = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, frm, to, raw):
        self.sent.append((frm, to, raw))


@pytest.fixture
def smtp_spy(monkeypatch):
    import smtplib

    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP.instances


@pytest.fixture
def smtp_settings(monkeypatch):
    from app.core.config import settings

    def configure(**overrides):
        defaults = {
            "SMTP_HOST": "mail.example.test",
            "SMTP_PORT": 587,
            "SMTP_USER": "robot@example.test",
            "SMTP_PASSWORD": "secret",
            "SMTP_FROM": "",
            "SMTP_FROM_NAME": "Vimana",
            "SMTP_REPLY_TO": "",
        }
        for key, value in {**defaults, **overrides}.items():
            monkeypatch.setattr(settings, key, value)

    return configure


def test_send_email_skips_when_smtp_unconfigured(smtp_spy, smtp_settings):
    from app.core.email import send_email

    smtp_settings(SMTP_HOST="")
    send_email("someone@example.test", "subject", "body")

    assert smtp_spy == [], "no connection may be opened without a configured host"


def test_send_email_skips_without_recipient(smtp_spy, smtp_settings):
    from app.core.email import send_email

    smtp_settings()
    send_email("", "subject", "body")

    assert smtp_spy == []


def test_from_falls_back_to_smtp_user(smtp_spy, smtp_settings):
    from app.core.email import send_email

    smtp_settings(SMTP_FROM="", SMTP_FROM_NAME="")
    send_email("someone@example.test", "subject", "body")

    envelope_from, _, raw = smtp_spy[0].sent[0]
    assert envelope_from == "robot@example.test"
    assert message_from_string(raw)["From"] == "robot@example.test"


def test_from_prefers_smtp_from_and_carries_display_name(smtp_spy, smtp_settings):
    from app.core.email import send_email

    smtp_settings(SMTP_FROM="vimana@dealvault.club", SMTP_FROM_NAME="Vimana")
    send_email("someone@example.test", "subject", "body")

    envelope_from, recipients, raw = smtp_spy[0].sent[0]
    msg = message_from_string(raw)
    assert msg["From"] == "Vimana <vimana@dealvault.club>"
    # Envelope and header must agree: a mismatch is what costs SPF alignment.
    assert envelope_from == "vimana@dealvault.club"
    assert recipients == ["someone@example.test"]
    # Authentication still happens as the submission account, not the sender.
    assert smtp_spy[0].logged_in == ("robot@example.test", "secret")


def test_non_ascii_display_name_is_header_encoded(smtp_spy, smtp_settings):
    from app.core.email import send_email

    smtp_settings(SMTP_FROM="vimana@dealvault.club", SMTP_FROM_NAME="Вимана")
    send_email("someone@example.test", "subject", "body")

    _, _, raw = smtp_spy[0].sent[0]
    header = message_from_string(raw)["From"]
    assert "Вимана" not in header, "raw UTF-8 in a header gets messages dropped"
    assert header.startswith("=?utf-8?"), header
    assert "vimana@dealvault.club" in header


def test_reply_to_is_set_only_when_configured(smtp_spy, smtp_settings):
    from app.core.email import send_email

    smtp_settings(SMTP_REPLY_TO="hello@dealvault.club")
    send_email("someone@example.test", "subject", "body")
    assert message_from_string(smtp_spy[0].sent[0][2])["Reply-To"] == "hello@dealvault.club"

    smtp_settings(SMTP_REPLY_TO="")
    send_email("someone@example.test", "subject", "body")
    assert message_from_string(smtp_spy[1].sent[0][2])["Reply-To"] is None
