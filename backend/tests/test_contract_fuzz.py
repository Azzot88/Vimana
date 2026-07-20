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

from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

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
    # 503 is a legitimate documented state (e.g. "telegram not configured",
    # "nostr publish disabled") — only real 5xx (500/501/502/504) count as bugs.
    if response.status_code == 503:
        return
    assert response.status_code < 500, (
        f"5xx from {case.method} {case.path}\n"
        f"  body: {case.body!r}\n"
        f"  query: {case.query!r}\n"
        f"  response ({response.status_code}): {response.text[:400]}"
    )


# ─────────────────────────────────────────────────────────────
# pt.2 — authed fuzz (regular user + superuser)
# ─────────────────────────────────────────────────────────────


async def _create_user_direct(session_maker, prefix: str, role: str = "user") -> str:
    """Insert a user row directly into the test DB (bypass HTTP + FastAPI +
    override_db timing). Returns a signed JWT for that user.

    Why not use `_register_and_login` via ASGI? Session-scoped fixtures run
    BEFORE function-scoped `override_db` (autouse). At that point FastAPI's
    `get_db` still points at the production DB — the ASGI register would
    write to the wrong place, JWT would reference a non-existent user in
    the test DB, endpoints would 401 (looked like "passing" fuzz).
    """
    email = f"fuzz-{prefix}-{uuid.uuid4().hex[:8]}@e2e.vimana.local"
    nsec_hex, npub_hex = generate_keypair()
    nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)

    async with session_maker() as db:
        user = User(
            email=email,
            password_hash=hash_password("fuzz-pass-1"),
            display_name=f"Fuzz {prefix.title()}",
            can_carry=True,
            can_send=True,
            active_mode="sender",
            nostr_pubkey=npub_hex,
            nsec_encrypted=nsec_ct,
            nsec_nonce=nsec_nonce,
            key_self_custody=False,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = str(user.id)

    return create_access_token(user_id)


@pytest_asyncio.fixture(scope="session")
async def fuzz_user_token(session_maker):
    """Regular user token — cached for the whole session."""
    return await _create_user_direct(session_maker, "user", role="user")


@pytest_asyncio.fixture(scope="session")
async def fuzz_superuser_token(session_maker):
    """Superuser token — cached for the whole session. Role set at insert
    time so we don't have to update afterwards."""
    return await _create_user_direct(session_maker, "super", role="superuser")


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
    # 503 is a legitimate documented state (e.g. "telegram not configured",
    # "nostr publish disabled") — only real 5xx (500/501/502/504) count as bugs.
    if response.status_code == 503:
        return
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
    # 503 is a legitimate documented state (e.g. "telegram not configured",
    # "nostr publish disabled") — only real 5xx (500/501/502/504) count as bugs.
    if response.status_code == 503:
        return
    assert response.status_code < 500, (
        f"5xx (authed superuser) from {case.method} {case.path}\n"
        f"  body: {case.body!r}\n"
        f"  query: {case.query!r}\n"
        f"  response ({response.status_code}): {response.text[:400]}"
    )
