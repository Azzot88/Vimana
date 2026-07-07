"""T1.19 block 4: global exception handler, logging, request_id."""
import logging


async def test_health_response_has_request_id_header(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID"), "response must carry X-Request-ID header"


async def test_client_provided_request_id_is_echoed(client):
    resp = await client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.headers.get("X-Request-ID") == "trace-abc-123"


async def test_http_exception_response_includes_request_id(client):
    resp = await client.post(
        "/api/auth/login", json={"login": "ghost@vimana.test", "password": "x"}
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Invalid credentials"
    assert "request_id" in body and len(body["request_id"]) > 0


async def test_validation_error_response_includes_request_id(client):
    resp = await client.post(
        "/api/auth/register",
        json={"password": "too-short", "display_name": "X"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], list)
    assert "request_id" in body


async def test_unhandled_exception_returns_stable_shape_and_logs(client, caplog):
    from app.main import app

    @app.get("/__boom__")
    async def _boom():
        raise RuntimeError("kaboom")

    with caplog.at_level(logging.ERROR, logger="app.main"):
        resp = await client.get("/__boom__")

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "Internal server error"
    assert body["error"]["request_id"]
    assert any("Unhandled exception" in rec.message for rec in caplog.records)

    # Cleanup: remove the injected route so it doesn't leak into other tests
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/__boom__"]


async def test_silent_telegram_send_logs_failure(monkeypatch, caplog):
    from app.core import telegram as tg_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "fake-bot-token")

    def _raise(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(tg_module.httpx, "post", _raise)

    with caplog.at_level(logging.ERROR, logger="app.core.telegram"):
        tg_module.send_telegram("999", "hi")

    assert any("Telegram sendMessage failed" in rec.message for rec in caplog.records)
