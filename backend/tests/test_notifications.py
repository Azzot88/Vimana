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
