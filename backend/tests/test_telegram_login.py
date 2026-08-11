"""T3.27 — signing in through Telegram, where the transport runs backwards.

Every other channel is told where to deliver. A bot cannot write to somebody who
has never written to it, so this exchange starts with a link, the code is minted
only when Start is pressed, and the account is resolved from a chat id the site
never sees.

The suite drives all three legs — request, webhook, verify — rather than calling
the helpers, because the thing worth pinning is that they agree about one row.
"""
import uuid as uuidlib

import pytest
from sqlalchemy import select

from tests.conftest import SEED_PASSWORD, make_account, unique_email

BOT = "vimana_test_bot"


@pytest.fixture(autouse=True)
def bot_configured(monkeypatch):
    """The bot is a deployment fact, and the suite must not depend on the
    machine's `.env` — `T_TEST.7` is the record of what that costs: five tests
    passed for a month because the feature was switched off underneath them."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", BOT, raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "test-token", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("CHANNEL_TELEGRAM_ENABLED", raising=False)


@pytest.fixture
def sent_codes(monkeypatch):
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: sent.append(a))
    return sent


@pytest.fixture
def chat_replies(monkeypatch):
    from app.tasks import notifications as notif

    said = []
    monkeypatch.setattr(notif.send_telegram_chat, "delay", lambda *a: said.append(a))
    return said


async def _link(client):
    resp = await client.post(
        "/api/auth/otp/request", json={"identifier": "", "channel": "telegram"}
    )
    assert resp.status_code == 202
    return resp.json()["nonce"]


async def _start(client, nonce, chat_id="chat-777", first_name="Пётр"):
    return await client.post(
        "/api/telegram/webhook",
        json={
            "update_id": 1,
            "message": {
                "chat": {"id": chat_id},
                "text": f"/start {nonce}",
                "from": {"first_name": first_name, "language_code": "ru"},
            },
        },
    )


async def _verify(client, nonce, code):
    return await client.post(
        "/api/auth/otp/verify",
        json={"identifier": nonce, "code": code, "channel": "telegram"},
    )


# ── the happy path, in three legs ────────────────────────────────────────────


async def test_a_request_hands_back_a_link_and_no_code(client, sent_codes):
    """Nothing is delivered yet — there is nowhere to deliver to."""
    resp = await client.post(
        "/api/auth/otp/request", json={"identifier": "", "channel": "telegram"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["link"] == f"https://t.me/{BOT}?start={body['nonce']}"
    assert sent_codes == []


async def test_start_mints_the_code_and_records_the_chat(
    client, sent_codes, session_maker
):
    from app.models.contact import VerificationChallenge

    nonce = await _link(client)
    assert (await _start(client, nonce)).status_code == 200

    channel, target, code, _locale = sent_codes[-1]
    assert channel == "telegram"
    assert target == "chat-777"
    assert code.isdigit() and len(code) == 6

    async with session_maker() as db:
        row = (
            await db.execute(
                select(VerificationChallenge).where(
                    VerificationChallenge.value == nonce
                )
            )
        ).scalars().first()
    assert row.resolved_value == "chat-777"
    assert row.code_hash is not None


async def test_the_code_creates_an_account_with_a_telegram_contact(
    client, sent_codes, session_maker
):
    from app.models.contact import UserContact
    from app.models.user import User

    nonce = await _link(client)
    await _start(client, nonce)
    resp = await _verify(client, nonce, sent_codes[-1][2])

    assert resp.status_code == 200
    assert resp.json()["created"] is True

    async with session_maker() as db:
        contact = (
            await db.execute(
                select(UserContact).where(
                    UserContact.channel == "telegram",
                    UserContact.value == "chat-777",
                )
            )
        ).scalars().first()
        assert contact is not None
        assert contact.verified is True, "pressing Start is the proof"
        assert contact.is_login is True

        user = await db.get(User, contact.user_id)
        assert user.telegram_chat_id == "chat-777"
        assert user.email is None, "an account born from a chat has no address"
        assert user.display_name == "Пётр", "the name Telegram already knew"
        assert user.nostr_pubkey, "same shape as every other account (T3.12)"


async def test_a_second_sign_in_finds_the_same_account(client, sent_codes):
    """Not a second account: the chat is the identity here."""
    first = await _link(client)
    await _start(client, first)
    one = await _verify(client, first, sent_codes[-1][2])

    second = await _link(client)
    await _start(client, second)
    two = await _verify(client, second, sent_codes[-1][2])

    assert two.status_code == 200
    assert two.json()["created"] is False
    assert one.json()["access_token"] != two.json()["access_token"]


async def test_an_account_that_linked_telegram_before_is_adopted(
    client, sent_codes, session_maker
):
    """Accounts linked before T3.25 have the column and no contact row. Creating
    a second account for them would split one person in two."""
    from app.models.user import User

    email = unique_email("tg-legacy")
    made = await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Legacy"}
    )
    async with session_maker() as db:
        user = await db.get(User, uuidlib.UUID(made.json()["id"]))
        user.telegram_chat_id = "chat-legacy"
        await db.commit()

    nonce = await _link(client)
    await _start(client, nonce, chat_id="chat-legacy")
    resp = await _verify(client, nonce, sent_codes[-1][2])

    assert resp.status_code == 200
    assert resp.json()["created"] is False

    async with session_maker() as db:
        again = await db.get(User, uuidlib.UUID(made.json()["id"]))
        assert again.email == email, "the same account, not a new one"


# ── the refusals ─────────────────────────────────────────────────────────────


async def test_telegram_connected_from_the_profile_signs_in_the_same_account(
    client, sent_codes, session_maker
):
    """A real widening, and the alternative is worse: if sign-in did not
    recognise a chat connected from the profile, the person would get a second
    account instead of their own."""
    from app.models.user import User

    email = unique_email("tg-connected")
    made = await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Connected"}
    )
    token = (
        await client.post(
            "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
        )
    ).json()["access_token"]

    link = await client.get(
        "/api/telegram/connect", headers={"Authorization": f"Bearer {token}"}
    )
    connect_token = link.json()["link"].split("start=")[1]
    await _start(client, connect_token, chat_id="chat-profile")

    nonce = await _link(client)
    await _start(client, nonce, chat_id="chat-profile")
    resp = await _verify(client, nonce, sent_codes[-1][2])

    assert resp.status_code == 200
    assert resp.json()["created"] is False
    async with session_maker() as db:
        again = await db.get(User, uuidlib.UUID(made.json()["id"]))
        assert again.email == email


async def test_a_code_cannot_be_spent_before_start(client):
    """The link exists, nobody pressed Start: there is no code to be wrong."""
    nonce = await _link(client)
    resp = await _verify(client, nonce, "000000")
    assert resp.status_code == 400


async def test_a_second_start_on_the_same_nonce_sends_nothing(
    client, sent_codes, chat_replies
):
    nonce = await _link(client)
    await _start(client, nonce)
    assert len(sent_codes) == 1

    await _start(client, nonce)
    assert len(sent_codes) == 1, "the exchange was already minted"
    assert chat_replies[-1][1] == "stale"


async def test_an_invented_nonce_gets_the_stale_answer(client, sent_codes, chat_replies):
    await _start(client, "not-a-nonce-anybody-issued")
    assert sent_codes == []
    assert chat_replies[-1][1] == "stale"


async def test_a_wrong_code_is_refused(client, sent_codes):
    nonce = await _link(client)
    await _start(client, nonce)
    assert (await _verify(client, nonce, "111111")).status_code == 400


async def test_an_expired_exchange_sends_no_code(client, sent_codes, session_maker):
    """The window belongs to the link as much as to the code."""
    from datetime import datetime, timedelta, timezone

    from app.models.contact import VerificationChallenge

    nonce = await _link(client)
    async with session_maker() as db:
        row = (
            await db.execute(
                select(VerificationChallenge).where(
                    VerificationChallenge.value == nonce
                )
            )
        ).scalars().first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

    await _start(client, nonce)
    assert sent_codes == []


async def test_the_code_window_starts_when_the_code_is_sent(client, sent_codes, session_maker):
    """Somebody who opens the link ten minutes later still gets a full window to
    type what they were just handed."""
    from datetime import datetime, timezone

    from app.core.contact_verification import CODE_TTL
    from app.models.contact import VerificationChallenge

    nonce = await _link(client)
    await _start(client, nonce)

    async with session_maker() as db:
        row = (
            await db.execute(
                select(VerificationChallenge).where(
                    VerificationChallenge.value == nonce
                )
            )
        ).scalars().first()
        expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    remaining = expires - datetime.now(timezone.utc)
    assert remaining > CODE_TTL / 2


async def test_an_email_code_cannot_be_spent_as_a_telegram_one(client, monkeypatch):
    """The channel decides which exchange is looked up; a nonce and an address
    live in different rows and must not be interchangeable."""
    from app.tasks import notifications as notif

    codes = []
    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: codes.append(a))

    email = unique_email("tg-crosswire")
    await client.post(
        "/api/auth/otp/request",
        json={"identifier": email, "channel": "email", "locale": "en"},
    )
    resp = await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": codes[-1][2], "channel": "telegram"},
    )
    assert resp.status_code == 400


# ── what the screen is told ──────────────────────────────────────────────────


async def test_an_empty_identifier_offers_telegram(client):
    """Asked on load, before anything is typed: the screen must not decide on
    its own whether our bot exists."""
    resp = await client.post("/api/auth/contact/channels", json={"identifier": ""})
    assert resp.json()["channels"] == ["telegram"]


async def test_an_unconfigured_bot_offers_nothing(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "", raising=False)
    resp = await client.post("/api/auth/contact/channels", json={"identifier": ""})
    assert resp.json()["channels"] == []


async def test_requesting_a_link_without_a_bot_says_so(client, monkeypatch):
    """503, not a silent 202. The rule about answering identically protects
    facts about *accounts*; this is a fact about our own deployment, and hiding
    it leaves a button that quietly does nothing."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "", raising=False)
    resp = await client.post(
        "/api/auth/otp/request", json={"identifier": "", "channel": "telegram"}
    )
    assert resp.status_code == 503
