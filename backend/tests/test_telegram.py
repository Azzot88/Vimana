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
