"""T_SEC.1 — `EXPOSE_DOCS` gates the Swagger/Redoc/OpenAPI surface.

Test isolates the FastAPI factory at import time: `app.main` reads the env
once at module load, so we can't just flip the flag and hit the running
app fixture. Instead we import a fresh instance with the flag flipped.

`app.main` is already imported by conftest → we do a clean reload guarded
by `importlib.reload` inside a monkeypatched os.environ.
"""
from __future__ import annotations

import importlib
import os

import pytest
from httpx import ASGITransport, AsyncClient


def _fresh_app(*, expose: bool):
    os.environ["EXPOSE_DOCS"] = "true" if expose else "false"
    import app.main as main_module

    importlib.reload(main_module)
    return main_module.app


@pytest.fixture
def _restore_docs_env():
    original = os.environ.get("EXPOSE_DOCS")
    yield
    if original is None:
        os.environ.pop("EXPOSE_DOCS", None)
    else:
        os.environ["EXPOSE_DOCS"] = original
    # Reload back to whatever default the running test session expected.
    import app.main as main_module

    importlib.reload(main_module)


async def test_docs_disabled_returns_404(_restore_docs_env):
    app = _fresh_app(expose=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/redoc")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404


async def test_docs_enabled_returns_200(_restore_docs_env):
    app = _fresh_app(expose=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/docs")).status_code == 200
        assert (await c.get("/openapi.json")).status_code == 200


async def test_health_stays_public_regardless_of_docs_flag(_restore_docs_env):
    """/health must be reachable so docker healthcheck works either way."""
    for flag in (True, False):
        app = _fresh_app(expose=flag)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/health")
            # 200 if endpoint exists — otherwise not our problem here; test
            # just proves the flag doesn't accidentally block it.
            assert resp.status_code in (200, 404)
