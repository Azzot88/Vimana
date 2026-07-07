"""T1.19 block 3: CORS, rate limiting, Telegram webhook secret."""
import uuid as uuidlib

import pytest

from app.core.rate_limit import limiter


@pytest.fixture
def enable_rate_limit():
    was_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = was_enabled


async def test_login_rate_limit_triggers_429(client, enable_rate_limit):
    email = f"rl-{uuidlib.uuid4().hex[:6]}@vimana.test"
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "rl-pass-1", "display_name": "RL"},
    )
    codes = []
    for _ in range(8):
        resp = await client.post(
            "/api/auth/login", json={"login": email, "password": "wrong-pass"}
        )
        codes.append(resp.status_code)
    assert 429 in codes, codes


async def test_waitlist_rate_limit_triggers_429(client, enable_rate_limit):
    codes = []
    for i in range(6):
        email = f"rl-wl-{i}-{uuidlib.uuid4().hex[:6]}@vimana.test"
        resp = await client.post("/api/waitlist", json={"email": email})
        codes.append(resp.status_code)
    assert 429 in codes, codes


async def test_telegram_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-webhook-secret")
    resp = await client.post(
        "/api/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 1}, "text": "hi"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert resp.status_code == 403


async def test_telegram_webhook_accepts_correct_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-webhook-secret")
    resp = await client.post(
        "/api/telegram/webhook",
        json={"update_id": 2, "message": None},
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-webhook-secret"},
    )
    assert resp.status_code == 200


async def test_telegram_webhook_no_secret_configured_allows_all(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    resp = await client.post(
        "/api/telegram/webhook",
        json={"update_id": 3, "message": None},
    )
    assert resp.status_code == 200
