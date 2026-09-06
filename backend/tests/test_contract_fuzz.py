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
from hypothesis import HealthCheck, settings

from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

# T3.11.15 / T3.11.07 — `filter_too_much` is suppressed, and it is worth being
# precise about what that does and does not mean.
#
# The health check fires when Hypothesis discards far more generated examples
# than it keeps. It started firing on `POST /api/trips` when the trip body grew
# a **required array of nested objects** (`legs`) alongside several nullable
# `$ref` objects (`handover_origin`, `handover_destination`): that shape is more
# than `hypothesis-jsonschema` can encode directly, so it falls back to
# generating and filtering, and the keep rate collapses. Measured on the run
# that caught it: 50 discarded against 4–8 kept.
#
# This is a statement about generation efficiency, not about the product. The
# assertion these tests make — no endpoint returns a 5xx — is unchanged, and the
# suppression does not weaken it. What it does cost is **coverage on that one
# endpoint**: fewer distinct bodies actually reach the handler per run, so the
# fuzz is thinner there than the `max_examples` number suggests. Named here so
# nobody reads a green fuzz run as more than it is.
#
# `deadline=None` for the reason it always was: Hypothesis's 200 ms default is
# too tight for ASGI plus a database round trip.
#
# The alternative was to flatten a schema that is correct in order to please a
# generator, which is the wrong way round.
FUZZ = settings(deadline=None, suppress_health_check=[HealthCheck.filter_too_much])

# Excluded from everyday runs via `-m "not fuzz"` (registered in pytest.ini).
# schemathesis drives the ASGI app from sync code, spinning up a fresh event
# loop per request, so Redis connections outlive the loop that made them and
# their finalizers fail. Filtered in `pytest.ini` by the exact finalizer name —
# see the comment on the `AbstractConnection.__del__` entry there.
pytestmark = pytest.mark.fuzz

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
@settings(FUZZ, max_examples=15)
def test_no_server_errors_unauthed(case):
    """No endpoint returns 500 for any generated input.

    Settings come from `FUZZ` above, which explains both of them.
    `case.call()` uses the ASGI transport automatically because the schema was
    created with `app=app`.
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
            roles=[] if role == "user" else [role],
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
@settings(FUZZ, max_examples=10)
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
@settings(FUZZ, max_examples=10)
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
