import uuid as uuidlib

from app.models.user import User


async def test_webhook_no_message_returns_ok(client):
    resp = await client.post("/api/telegram/webhook", json={"update_id": 1})
    assert resp.status_code == 200
    assert resp.json() == {"ok": "no message"}


async def test_webhook_start_command_links_chat_id(client, session_maker):
    email = f"tg-link-{uuidlib.uuid4().hex[:8]}@vimana.test"
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "tg-pw-test-1", "display_name": "TG Link"},
    )
    assert reg.status_code == 201
    user_id = uuidlib.UUID(reg.json()["id"])

    token = f"tg-token-{uuidlib.uuid4().hex[:16]}"
    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.telegram_link_token = token
        await db.commit()

    chat_id = 100_000_000 + int(uuidlib.uuid4().int % 10_000_000)
    resp = await client.post(
        "/api/telegram/webhook",
        json={
            "update_id": 42,
            "message": {"chat": {"id": chat_id}, "text": f"/start {token}"},
        },
    )
    assert resp.status_code == 200

    async with session_maker() as db:
        user = await db.get(User, user_id)
        assert user.telegram_chat_id == str(chat_id)
        assert user.notify_telegram is True
        assert user.telegram_link_token is None


async def test_webhook_unknown_token_ignored(client):
    resp = await client.post(
        "/api/telegram/webhook",
        json={
            "update_id": 100,
            "message": {"chat": {"id": 111}, "text": "/start nonexistent-token-000"},
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": "processed"}


async def test_connect_returns_503_when_bot_not_configured(client, carrier_headers):
    resp = await client.get("/api/telegram/connect", headers=carrier_headers)
    assert resp.status_code == 503


# ── T_UX.12 · the webhook must be trustworthy in both directions ─────────────


def test_set_webhook_carries_the_secret(monkeypatch):
    """Without it Telegram sends no header and every real update gets 403."""
    import app.core.telegram as tg

    sent = {}
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(
        tg.httpx,
        "post",
        lambda url, json, timeout: sent.update(url=url, json=json)
        or type("R", (), {"json": lambda self: {"ok": True}})(),
    )

    tg.set_webhook("https://example.test/api/telegram/webhook")

    assert sent["json"]["secret_token"] == "s3cret"
    assert sent["json"]["allowed_updates"] == ["message"]


def test_set_webhook_omits_the_secret_when_unset(monkeypatch):
    import app.core.telegram as tg

    sent = {}
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(
        tg.httpx,
        "post",
        lambda url, json, timeout: sent.update(json=json)
        or type("R", (), {"json": lambda self: {"ok": True}})(),
    )

    tg.set_webhook("https://example.test/api/telegram/webhook")

    assert "secret_token" not in sent["json"]


async def test_set_webhook_endpoint_is_superuser_only(client, session_maker):
    """An ordinary session could re-point the bot at a stranger's server."""
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("tg-plain")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "tg"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    anon = await client.post(
        "/api/telegram/set_webhook", params={"webhook_url": "https://evil.test/hook"}
    )
    assert anon.status_code == 401

    resp = await client.post(
        "/api/telegram/set_webhook",
        params={"webhook_url": "https://evil.test/hook"},
        headers=hdr,
    )
    assert resp.status_code == 403


# ── T_UX.12 pt.2 · every branch answers ──────────────────────────────────────


async def test_start_with_valid_token_confirms_in_the_account_language(
    client, session_maker, monkeypatch
):
    """Silence was the complaint: pressing Start worked and looked like nothing."""
    from app.tasks import notifications as notif

    queued = []
    monkeypatch.setattr(
        notif.send_telegram_chat, "delay", lambda *a: queued.append(a)
    )

    from sqlalchemy import select

    from app.models.user import User
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("tg-link")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "tg",
              "locale": "fr"},
    )
    token = f"tok-{uuidlib.uuid4().hex}"
    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        user.telegram_link_token = token
        await db.commit()

    resp = await client.post(
        "/api/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 999}, "text": f"/start {token}"}},
    )
    assert resp.status_code == 200
    assert queued == [("999", "linked", "fr")], "the reply follows the account's language"


async def test_start_with_stale_token_says_so(client, monkeypatch):
    """An expired link must not be indistinguishable from a broken bot."""
    from app.tasks import notifications as notif

    queued = []
    monkeypatch.setattr(notif.send_telegram_chat, "delay", lambda *a: queued.append(a))

    await client.post(
        "/api/telegram/webhook",
        json={
            "update_id": 2,
            "message": {"chat": {"id": 5}, "text": "/start nope",
                        "from": {"language_code": "es"}},
        },
    )
    assert queued == [("5", "stale", "es")]


async def test_bare_start_explains_what_the_bot_is(client, monkeypatch):
    from app.tasks import notifications as notif

    queued = []
    monkeypatch.setattr(notif.send_telegram_chat, "delay", lambda *a: queued.append(a))

    await client.post(
        "/api/telegram/webhook",
        json={"update_id": 3, "message": {"chat": {"id": 7}, "text": "/start"}},
    )
    assert queued == [("7", "hello", None)]


def test_chat_catalogue_is_complete_in_every_locale():
    """Same guard the letters have: a missing key must fail here, not in a chat."""
    from app.core.email_templates import CHAT_KINDS, LOCALES, chat_message

    for locale in LOCALES:
        for kind in CHAT_KINDS:
            assert chat_message(kind, locale).strip(), f"{locale}/{kind}"


def test_chat_message_falls_back_like_a_letter():
    from app.core.email_templates import chat_message

    assert chat_message("hello", "kl") == chat_message("hello", "en")
    assert chat_message("hello", None) == chat_message("hello", "en")
