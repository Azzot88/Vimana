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


def test_from_shows_the_brand_name(smtp_spy):
    from app.core.email import FROM_DISPLAY_NAME, send_email

    opened = smtp_spy(465)
    send_email("someone@example.test", "subject", "body")

    envelope_from, _, raw = opened[0].sent[0]
    header = message_from_string(raw)["From"]
    # The name is non-ASCII (em dash), so it must travel as an encoded word —
    # raw UTF-8 in a header is dropped by some receivers.
    assert FROM_DISPLAY_NAME not in header, "the name must be RFC 2047-encoded"
    assert header.startswith("=?utf-8?"), header
    assert "vimana@example.test" in header
    # Routing is unaffected: the envelope carries the bare address.
    assert envelope_from == "vimana@example.test"


def test_message_carries_date_and_message_id(smtp_spy):
    from app.core.email import send_email

    opened = smtp_spy(465)
    send_email("someone@example.test", "subject", "body")

    msg = message_from_string(opened[0].sent[0][2])
    # Both are mandatory per RFC 5322 and both are worth spam points when
    # missing; nothing downstream fills them in for us.
    assert msg["Date"], "a message with no Date is scored as spam"
    message_id = msg["Message-ID"]
    assert message_id, "a message with no Message-ID is scored as spam"
    assert message_id.startswith("<") and message_id.endswith(">")
    assert message_id.endswith("@example.test>"), (
        "the id must be anchored to the sender's domain, not the container hostname"
    )


def test_no_connection_without_configuration(smtp_spy, monkeypatch):
    from app.core.config import settings
    from app.core.email import send_email

    opened = smtp_spy(465)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    send_email("someone@example.test", "subject", "body")

    assert opened == [], "an unconfigured host must not reach the network"


# ── T_UX.8 · waitlist letters ────────────────────────────────────────────────


def test_send_email_reports_delivery(smtp_spy):
    """The boolean is the whole point: a caller writes a `sent` mark from it."""
    from app.core.email import send_email

    smtp_spy(465)
    assert send_email("someone@example.test", "subject", "body") is True


def test_send_email_reports_silence_when_unconfigured(smtp_spy, monkeypatch):
    from app.core.config import settings
    from app.core.email import send_email

    smtp_spy(465)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert send_email("someone@example.test", "subject", "body") is False, (
        "an unconfigured transport must not look like a delivered message"
    )


@pytest.fixture
def mail_spy(monkeypatch):
    """Record `send_email` calls; let the test decide whether they land.

    The `channel_calls` fixture above returns None from its lambda, which reads
    as "not delivered" — correct for the fire-and-forget notifications it was
    written for, useless here, where the return value decides whether a row is
    marked.
    """
    sent: list[tuple[str, str, str]] = []
    state = {"delivers": True}
    from app.tasks import notifications as notif

    def _send(to, subject, body):
        sent.append((to, subject, body))
        return state["delivers"]

    monkeypatch.setattr(notif, "send_email", _send)
    return sent, state


def _new_waitlist_entry(maker, *, sent_at=None):
    from app.models.waitlist import WaitlistEntry

    email = f"wl-{uuidlib.uuid4().hex[:10]}@vimana.test"
    with maker() as db:
        entry = WaitlistEntry(
            email=email, name="Tester", source="landing", confirmation_sent_at=sent_at
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return str(entry.id), email


def _confirmation_sent_at(maker, entry_id):
    from app.models.waitlist import WaitlistEntry

    with maker() as db:
        return db.get(WaitlistEntry, entry_id).confirmation_sent_at


def test_waitlist_letters_reach_visitor_and_owner(sync_test_session, mail_spy):
    from app.core.superuser import USER_ZERO_EMAIL
    from app.tasks.notifications import send_waitlist_emails

    sent, _ = mail_spy
    entry_id, email = _new_waitlist_entry(sync_test_session)

    send_waitlist_emails(entry_id)

    recipients = [c[0] for c in sent]
    assert email in recipients, "the person who signed up must be answered"
    assert USER_ZERO_EMAIL in recipients, "the owner must learn about the signup"


def test_waitlist_confirmation_promises_an_invite(sync_test_session, mail_spy):
    from app.tasks.notifications import send_waitlist_emails

    sent, _ = mail_spy
    entry_id, email = _new_waitlist_entry(sync_test_session)

    send_waitlist_emails(entry_id)

    body = next(c[2] for c in sent if c[0] == email)
    assert "приглашение" in body and "invite" in body, (
        "the letter must say what happens next, in both languages it is written in"
    )


def test_waitlist_marks_the_row_once_the_letter_lands(sync_test_session, mail_spy):
    from app.tasks.notifications import send_waitlist_emails

    entry_id, _ = _new_waitlist_entry(sync_test_session)
    send_waitlist_emails(entry_id)

    assert _confirmation_sent_at(sync_test_session, entry_id) is not None


def test_waitlist_does_not_mark_a_letter_that_never_left(sync_test_session, mail_spy):
    """The bug this guards against is the one that started the whole task."""
    from app.tasks.notifications import send_waitlist_emails

    _, state = mail_spy
    state["delivers"] = False
    entry_id, _ = _new_waitlist_entry(sync_test_session)

    send_waitlist_emails(entry_id)

    assert _confirmation_sent_at(sync_test_session, entry_id) is None, (
        "an unsent letter must leave the row pending, not marked done"
    )


def test_waitlist_letter_is_not_sent_twice(sync_test_session, mail_spy):
    from app.tasks.notifications import send_waitlist_emails

    sent, _ = mail_spy
    entry_id, email = _new_waitlist_entry(sync_test_session)

    send_waitlist_emails(entry_id)
    first = len([c for c in sent if c[0] == email])
    send_waitlist_emails(entry_id)

    assert len([c for c in sent if c[0] == email]) == first == 1


def test_waitlist_missing_entry_is_a_no_op(sync_test_session, mail_spy):
    from app.tasks.notifications import send_waitlist_emails

    sent, _ = mail_spy
    send_waitlist_emails(str(uuidlib.uuid4()))

    assert sent == []


def test_backfill_dry_run_sends_nothing(sync_test_session, mail_spy):
    from app.tasks.notifications import send_pending_waitlist_confirmations

    sent, _ = mail_spy
    _, email = _new_waitlist_entry(sync_test_session)

    result = send_pending_waitlist_confirmations(dry_run=True)

    assert sent == [], "a dry run that sends mail is not a dry run"
    assert email in result["addresses"]
    assert result["sent"] == 0


def test_backfill_writes_to_pending_and_skips_the_answered(sync_test_session, mail_spy):
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from app.tasks.notifications import send_pending_waitlist_confirmations

    sent, _ = mail_spy
    pending_id, pending_email = _new_waitlist_entry(sync_test_session)
    _, answered_email = _new_waitlist_entry(
        sync_test_session, sent_at=_dt.now(_tz.utc)
    )

    send_pending_waitlist_confirmations()

    recipients = [c[0] for c in sent]
    assert pending_email in recipients
    assert answered_email not in recipients, "nobody gets the same letter twice"
    assert _confirmation_sent_at(sync_test_session, pending_id) is not None


def test_backfill_is_safe_to_run_twice(sync_test_session, mail_spy):
    from app.tasks.notifications import send_pending_waitlist_confirmations

    sent, _ = mail_spy
    _, email = _new_waitlist_entry(sync_test_session)

    send_pending_waitlist_confirmations()
    after_first = len([c for c in sent if c[0] == email])
    send_pending_waitlist_confirmations()

    assert len([c for c in sent if c[0] == email]) == after_first == 1


def test_admin_fallback_logs_instead_of_raising(monkeypatch, caplog):
    """`logger` was undefined here — the fallback raised NameError instead."""
    import logging

    from app.tasks.notifications import notify_admins_scanner_down

    monkeypatch.setenv("ADMIN_TELEGRAM_CHAT_IDS", "")
    with caplog.at_level(logging.WARNING):
        notify_admins_scanner_down("clamd not answering")

    assert any("clamav down" in r.message % r.args for r in caplog.records)
