"""T_TEST.4 — schemathesis contract fuzz.

Runs schemathesis in-process against the FastAPI app (ASGI transport, no
external server needed). For every endpoint declared in `/openapi.json`,
schemathesis generates a batch of Hypothesis-style inputs and hits the
endpoint. We assert: **no unhandled 500s**.

pt.1 (unauthed): auth-required endpoints called without a token → should
    return 401/403, never 500.
pt.2 (authed): same fuzz but with a real Bearer token — exercises the
    handler bodies past the auth gate. Two flavors: regular user and
    superuser.

MVP scope for both:
- `not_a_server_error` check only (skip response_schema_conformance —
  OpenAPI is auto-generated and may have gaps).
- `max_examples=15` per endpoint (fast for local + CI).
- ~50 endpoints × 15 examples ≈ 750 requests per pass, ~30 sec.

pt.3 (deferred):
- Full checks (response_schema, status_code_conformance, content_type).
- HTML report artifact.
- OpenAPI drift check vs frontend TS types (`openapi-typescript`).
"""
from __future__ import annotations

import uuid
import warnings

import pytest
import pytest_asyncio
import schemathesis
from hypothesis import settings
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app

# schemathesis 3.39 still uses jsonschema.RefResolver internally, which
# jsonschema >= 4.18 deprecated. Not our code, fixed on their side in 4.x.
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"schemathesis\..*",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*RefResolver.*",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*RefResolutionError.*",
)

# FastAPI defaults to OpenAPI 3.1.0; schemathesis 3.39 only fully supports
# 3.0.x. We downgrade the version string + force the 3.0 loader.
_raw_schema = app.openapi()
_raw_schema["openapi"] = "3.0.3"
schema = schemathesis.from_dict(_raw_schema, app=app, force_schema_version="30")


# ─────────────────────────────────────────────────────────────
# pt.1 — unauthed fuzz
# ─────────────────────────────────────────────────────────────


@schema.parametrize()
@settings(max_examples=15, deadline=None)
def test_no_server_errors_unauthed(case):
    """No endpoint returns 500 for any generated input.

    `deadline=None` because Hypothesis's default 200ms deadline is too tight
    for ASGI + DB roundtrips. `case.call()` uses the ASGI transport
    automatically because the schema was created with `app=app`.
    """
    response = case.call()
    assert response.status_code < 500, (
        f"5xx from {case.method} {case.path}\n"
        f"  body: {case.body!r}\n"
        f"  query: {case.query!r}\n"
        f"  response ({response.status_code}): {response.text[:400]}"
    )


# ─────────────────────────────────────────────────────────────
# pt.2 — authed fuzz (regular user + superuser)
# ─────────────────────────────────────────────────────────────


async def _register_and_login(ac: AsyncClient, prefix: str) -> str:
    email = f"fuzz-{prefix}-{uuid.uuid4().hex[:8]}@e2e.vimana.local"
    await ac.post(
        "/api/auth/register",
        json={"email": email, "password": "fuzz-pass-1", "display_name": prefix.title()},
    )
    login = await ac.post(
        "/api/auth/login", json={"login": email, "password": "fuzz-pass-1"}
    )
    return login.json()["access_token"], email


@pytest_asyncio.fixture(scope="session")
async def fuzz_user_token():
    """Register a plain user once for the whole session. Bearer used to
    fuzz endpoints past the auth gate."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        token, _email = await _register_and_login(ac, "user")
        return token


@pytest_asyncio.fixture(scope="session")
async def fuzz_superuser_token():
    """Register + promote to superuser once for the whole session. Exercises
    admin-only endpoints past both auth and permission gates.

    Uses a fully isolated engine for the role UPDATE — sharing the
    conftest's session_maker leaves asyncpg connections in a stuck state
    ("another operation is in progress") when override_db later tries to
    reuse the same pool. Direct SQL avoids ORM identity-map complications.
    """
    from tests.conftest import TEST_DATABASE_URL

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        _token, email = await _register_and_login(ac, "super")

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE users SET role = 'superuser' WHERE email = :email"),
                {"email": email},
            )
    finally:
        await engine.dispose()

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        relogin = await ac.post(
            "/api/auth/login", json={"login": email, "password": "fuzz-pass-1"}
        )
        return relogin.json()["access_token"]


@schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_no_server_errors_authed_user(case, fuzz_user_token):
    """Same fuzz as pt.1 but as a plain authenticated user. Exercises
    handler bodies past the 401 wall — catches bugs that only trip when a
    real user record is loaded (e.g. missing default fields, ORM lazy-load
    without greenlet, `current_user.foo` when foo can be None).
    """
    headers = {"Authorization": f"Bearer {fuzz_user_token}"}
    response = case.call(headers=headers)
    assert response.status_code < 500, (
        f"5xx (authed user) from {case.method} {case.path}\n"
        f"  body: {case.body!r}\n"
        f"  query: {case.query!r}\n"
        f"  response ({response.status_code}): {response.text[:400]}"
    )


@schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_no_server_errors_authed_superuser(case, fuzz_superuser_token):
    """Same fuzz as authed_user but as superuser. Hits `/admin/*` handlers
    that regular users get 403 on — most 5xx bugs in admin land will only
    surface here.
    """
    headers = {"Authorization": f"Bearer {fuzz_superuser_token}"}
    response = case.call(headers=headers)
    assert response.status_code < 500, (
        f"5xx (authed superuser) from {case.method} {case.path}\n"
        f"  body: {case.body!r}\n"
        f"  query: {case.query!r}\n"
        f"  response ({response.status_code}): {response.text[:400]}"
    )
