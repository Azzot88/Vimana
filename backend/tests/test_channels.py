"""T3.26/T3.27 — the channel layer, and what each channel can honestly prove."""
import uuid as uuidlib

import pytest

from tests.conftest import SEED_PASSWORD, make_account, unique_email


def _number() -> str:
    return f"+97150{1_000_000 + uuidlib.uuid4().int % 9_000_000}"


# ── what a channel may claim ─────────────────────────────────────────────────


def test_email_identifier_offers_email_only():
    from app.core.channels import available_for

    assert available_for("someone@example.test") == ["email"]


def test_a_phone_can_be_proved_by_nothing(monkeypatch):
    """Two rules meeting, and the result is deliberate.

    Pressing Start proves control of a Telegram account, not of the number
    typed a minute earlier — so `telegram` was never offered for a phone. And
    since 2026-08-10 the channels that *did* reach a number are out of the plan
    (`T3.30`). Nothing is left that can prove a phone, so nothing is offered.
    """
    monkeypatch.setenv("CHANNEL_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_SMS_ENABLED", "true")
    from app.core.channels import available_for

    assert available_for(_number()) == []


def test_nothing_is_offered_for_nonsense():
    from app.core.channels import available_for

    assert available_for("not-an-identifier") == []
    assert available_for("0501234567") == [], "a number without a country code"


def test_a_disabled_channel_is_not_offered(monkeypatch):
    monkeypatch.setenv("CHANNEL_EMAIL_ENABLED", "false")
    from app.core.channels import available_for

    assert available_for("someone@example.test") == []


def test_paid_channels_are_off_unless_asked_for(monkeypatch):
    """A default that switches on a channel nobody has paid for fails in front
    of a person trying to sign in."""
    for flag in (
        "CHANNEL_SMS_ENABLED",
        "CHANNEL_WHATSAPP_ENABLED",
        "CHANNEL_TELEGRAM_GATEWAY_ENABLED",
    ):
        monkeypatch.delenv(flag, raising=False)
    from app.core.channels import enabled

    assert enabled("sms") is False
    assert enabled("whatsapp") is False
    assert enabled("telegram_gateway") is False
    assert enabled("email") is True


def test_gateway_proves_the_number_not_the_chat():
    from app.core.channels import proves

    assert proves("telegram_gateway") == "sms"
    assert proves("email") == "email"
    assert proves("telegram") == "telegram"


def test_a_disabled_channel_delivers_nothing(monkeypatch):
    monkeypatch.setenv("CHANNEL_SMS_ENABLED", "false")
    from app.core.channels import deliver

    assert deliver("sms", _number(), "123456", "en").sent is False


def test_email_delivery_carries_the_letter(monkeypatch):
    sent = {}
    import app.core.channels as ch

    monkeypatch.setenv("CHANNEL_EMAIL_ENABLED", "true")
    monkeypatch.setattr(
        "app.core.email.send_email",
        lambda to, subj, body, html=None: sent.update(to=to, subj=subj, body=body)
        or True,
    )
    result = ch.deliver("email", "who@example.test", "418305", "ru")
    assert result.sent is True
    assert "418305" in sent["body"]
    assert "Код" in sent["subj"], "the letter follows the requested language"


# ── the endpoints ────────────────────────────────────────────────────────────


async def test_channels_endpoint_answers_about_the_identifier(client):
    resp = await client.post(
        "/api/auth/contact/channels", json={"identifier": "who@example.test"}
    )
    assert resp.status_code == 200
    assert resp.json()["channels"] == ["email"]


async def test_channels_endpoint_needs_no_session(client):
    """It answers about an identifier, never about an account."""
    resp = await client.post(
        "/api/auth/contact/channels", json={"identifier": _number()}
    )
    assert resp.status_code == 200


async def test_request_code_answers_202_for_a_disabled_channel(client, monkeypatch):
    """A caller must not learn which channels we pay for."""
    monkeypatch.setenv("CHANNEL_SMS_ENABLED", "false")
    resp = await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": _number(), "channel": "sms"},
    )
    assert resp.status_code == 202


async def test_request_code_answers_202_for_nonsense(client):
    resp = await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": "garbage", "channel": "email"},
    )
    assert resp.status_code == 202


async def test_request_code_queues_a_delivery(client, monkeypatch):
    from app.tasks import notifications as notif

    queued = []
    monkeypatch.setattr(
        notif.send_channel_code, "delay", lambda *a: queued.append(a)
    )

    address = unique_email("chan-req")
    resp = await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": address, "channel": "email"},
    )
    assert resp.status_code == 202
    assert len(queued) == 1
    channel, value, code, _ = queued[0]
    assert (channel, value) == ("email", address)
    assert len(code) == 6


async def test_asking_twice_in_a_row_is_told_to_wait(client, monkeypatch):
    """The one thing this endpoint may answer differently: it is about the
    caller's own last request, and telling them to wait is its whole point."""
    from app.tasks import notifications as notif

    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: None)
    address = unique_email("chan-cool")
    first = await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": address, "channel": "email"},
    )
    assert first.status_code == 202
    second = await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": address, "channel": "email"},
    )
    assert second.status_code == 429


async def _session(client, email: str):
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": email[:8]},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_confirming_a_code_records_the_contact(
    client, session_maker, monkeypatch
):
    from sqlalchemy import select

    from app.models.contact import UserContact
    from app.tasks import notifications as notif

    queued = []
    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: queued.append(a))

    owner = unique_email("chan-own")
    hdr = await _session(client, owner)
    second = unique_email("chan-second")

    await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": second, "channel": "email"},
    )
    code = queued[-1][2]

    resp = await client.post(
        "/api/auth/contact/confirm",
        headers=hdr,
        json={"identifier": second, "code": code},
    )
    assert resp.status_code == 200
    assert resp.json()["channel"] == "email"

    async with session_maker() as db:
        row = (
            await db.execute(
                select(UserContact).where(
                    UserContact.channel == "email", UserContact.value == second
                )
            )
        ).scalar_one()
        assert row.verified_at is not None


async def test_a_wrong_code_is_refused_and_counted(client, monkeypatch):
    from app.tasks import notifications as notif

    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: None)
    hdr = await _session(client, unique_email("chan-wrong"))
    target = unique_email("chan-target")
    await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": target, "channel": "email"},
    )

    resp = await client.post(
        "/api/auth/contact/confirm",
        headers=hdr,
        json={"identifier": target, "code": "000000"},
    )
    assert resp.status_code == 400


async def test_confirming_without_a_pending_code_is_refused(client):
    hdr = await _session(client, unique_email("chan-none"))
    resp = await client.post(
        "/api/auth/contact/confirm",
        headers=hdr,
        json={"identifier": unique_email("nothing"), "code": "123456"},
    )
    assert resp.status_code == 400


async def test_confirming_requires_a_session(client):
    resp = await client.post(
        "/api/auth/contact/confirm",
        json={"identifier": "who@example.test", "code": "123456"},
    )
    assert resp.status_code == 401
