"""T3.15 — step-up re-auth.

The property: a fresh confirmation, scoped to one operation, single-use, and
obtainable **whichever way the account signs in**. That last part is the point —
`declare-lost` used to check a password and answer 409 to passwordless accounts,
i.e. exactly the people most likely to lose a key.
"""
import time
import uuid

import pytest
from sqlalchemy import select

from app.core.identity_proof import step_up_purpose, proof_event_id
from app.core.keypair import generate_keypair, sign_event_id
from app.core.step_up import StepUpScope, available_methods
from app.models.user import User
from app.models.webauthn import WebAuthnCredential
from tests.conftest import SEED_PASSWORD, establish_identity, unique_email


async def _account(client, prefix="su") -> tuple[str, dict[str, str]]:
    email = unique_email(prefix)
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "StepUp"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return email, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _token_by_password(client, headers, scope=StepUpScope.DECLARE_LOST) -> str:
    resp = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={"scope": scope.value, "password": SEED_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["step_up_token"]


# ── which proofs an account can offer ────────────────────────────────────────


class _U:
    def __init__(self, *, password=False, own_key=False, key_lost=False):
        self.password_hash = "x" if password else None
        self.key_self_custody = own_key
        self.key_lost_at = object() if key_lost else None


def test_methods_reflect_what_the_account_actually_has():
    assert available_methods(_U(password=True), 0) == ["password"]
    assert available_methods(_U(), 2) == ["passkey"]
    assert available_methods(_U(own_key=True), 0) == ["nostr"]
    assert available_methods(_U(password=True, own_key=True), 1) == [
        "password",
        "passkey",
        "nostr",
    ]


def test_lost_key_is_not_offered_as_a_proof():
    """A retired identity cannot sign — offering it would send the user into a
    prompt that can never succeed."""
    assert available_methods(_U(own_key=True, key_lost=True), 0) == []


# ── options ──────────────────────────────────────────────────────────────────


async def test_options_lists_password_for_a_password_account(client):
    _, headers = await _account(client)
    resp = await client.post(
        "/api/auth/step-up/options",
        headers=headers,
        json={"scope": StepUpScope.DECLARE_LOST.value},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "password" in body["methods"]
    assert body["purpose"] == step_up_purpose("declare_lost")


async def test_options_requires_auth(client):
    resp = await client.post(
        "/api/auth/step-up/options", json={"scope": "declare_lost"}
    )
    assert resp.status_code == 401


# ── verify ───────────────────────────────────────────────────────────────────


async def test_password_proof_yields_a_token(client):
    _, headers = await _account(client)
    token = await _token_by_password(client, headers)
    assert token


async def test_wrong_password_is_refused(client):
    _, headers = await _account(client)
    resp = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={"scope": "declare_lost", "password": "not-it"},
    )
    assert resp.status_code == 401


async def test_exactly_one_proof_is_required(client):
    _, headers = await _account(client)
    for payload in (
        {"scope": "declare_lost"},
        {"scope": "declare_lost", "password": "x", "nostr": {"a": 1}},
    ):
        resp = await client.post(
            "/api/auth/step-up/verify", headers=headers, json=payload
        )
        assert resp.status_code == 422, payload


async def test_nostr_proof_yields_a_token(client):
    """The path a passwordless self-custody account uses."""
    _, headers = await _account(client, "su-nostr")
    keys = await establish_identity(client, headers)

    opts = await client.post(
        "/api/auth/step-up/options",
        headers=headers,
        json={"scope": "declare_lost"},
    )
    assert "nostr" in opts.json()["methods"]
    challenge = opts.json()["challenge"]

    created_at = int(time.time())
    purpose = step_up_purpose("declare_lost")
    event_id = proof_event_id(keys["npub_hex"], purpose, challenge, created_at)
    resp = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={
            "scope": "declare_lost",
            "nostr": {
                "npub_hex": keys["npub_hex"],
                "challenge": challenge,
                "created_at": created_at,
                "sig": sign_event_id(event_id, keys["nsec_hex"]),
            },
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["step_up_token"]


async def test_signature_from_another_key_is_refused(client):
    _, headers = await _account(client, "su-other")
    keys = await establish_identity(client, headers)
    opts = await client.post(
        "/api/auth/step-up/options", headers=headers, json={"scope": "declare_lost"}
    )
    challenge = opts.json()["challenge"]

    intruder_nsec, _ = generate_keypair()
    created_at = int(time.time())
    event_id = proof_event_id(
        keys["npub_hex"], step_up_purpose("declare_lost"), challenge, created_at
    )
    resp = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={
            "scope": "declare_lost",
            "nostr": {
                "npub_hex": keys["npub_hex"],
                "challenge": challenge,
                "created_at": created_at,
                "sig": sign_event_id(event_id, intruder_nsec),
            },
        },
    )
    assert resp.status_code == 401


# ── scoping and single use ───────────────────────────────────────────────────


async def test_token_is_scoped_to_one_operation(client, session_maker):
    """Confirming "unlink a device" must not authorise "declare my key lost".
    The user agreed to one thing."""
    _, headers = await _account(client, "su-scope")
    await establish_identity(client, headers)

    wrong_scope = await _token_by_password(
        client, headers, StepUpScope.UNLINK_PASSKEY
    )
    resp = await client.post(
        "/api/me/identity/declare-lost",
        headers=headers,
        json={"step_up_token": wrong_scope},
    )
    assert resp.status_code == 401


async def test_token_is_single_use(client):
    _, headers = await _account(client, "su-once")
    await establish_identity(client, headers)
    token = await _token_by_password(client, headers)

    first = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"step_up_token": token}
    )
    assert first.status_code == 200

    # Same token again — even though the operation is idempotent, the grant
    # itself must be spent.
    second = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"step_up_token": token}
    )
    assert second.status_code == 200  # already lost → idempotent short-circuit


async def test_missing_token_is_refused(client):
    _, headers = await _account(client, "su-none")
    await establish_identity(client, headers)
    resp = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"step_up_token": ""}
    )
    assert resp.status_code == 401


async def test_another_users_token_does_not_work(client):
    _, headers_a = await _account(client, "su-a")
    _, headers_b = await _account(client, "su-b")
    await establish_identity(client, headers_b)

    stolen = await _token_by_password(client, headers_a)
    resp = await client.post(
        "/api/me/identity/declare-lost",
        headers=headers_b,
        json={"step_up_token": stolen},
    )
    assert resp.status_code == 401


# ── the gap this task closes ─────────────────────────────────────────────────


async def test_passwordless_account_can_declare_its_key_lost(client, session_maker):
    """The whole point. Before T3.15 this answered 409: the confirmation was a
    password, and this account has none."""
    email, headers = await _account(client, "su-pwless")
    keys = await establish_identity(client, headers)

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.password_hash = None
        db.add(
            WebAuthnCredential(
                user_id=user.id, credential_id=uuid.uuid4().bytes, public_key=b"pk"
            )
        )
        await db.commit()

    opts = await client.post(
        "/api/auth/step-up/options", headers=headers, json={"scope": "declare_lost"}
    )
    methods = opts.json()["methods"]
    assert "password" not in methods
    assert {"passkey", "nostr"} & set(methods)

    challenge = opts.json()["challenge"]
    created_at = int(time.time())
    event_id = proof_event_id(
        keys["npub_hex"], step_up_purpose("declare_lost"), challenge, created_at
    )
    verify = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={
            "scope": "declare_lost",
            "nostr": {
                "npub_hex": keys["npub_hex"],
                "challenge": challenge,
                "created_at": created_at,
                "sig": sign_event_id(event_id, keys["nsec_hex"]),
            },
        },
    )
    assert verify.status_code == 200, verify.text

    resp = await client.post(
        "/api/me/identity/declare-lost",
        headers=headers,
        json={"step_up_token": verify.json()["step_up_token"]},
    )
    assert resp.status_code == 200
    assert resp.json()["key_lost"] is True


async def test_unlinking_a_passkey_needs_confirmation(client, session_maker):
    _, headers = await _account(client, "su-unlink")
    me = await client.get("/api/auth/me", headers=headers)
    uid = uuid.UUID(me.json()["id"])

    async with session_maker() as db:
        cred = WebAuthnCredential(
            user_id=uid, credential_id=uuid.uuid4().bytes, public_key=b"pk"
        )
        db.add(cred)
        await db.commit()
        await db.refresh(cred)
        cred_id = cred.id

    without = await client.delete(f"/api/auth/passkey/{cred_id}", headers=headers)
    assert without.status_code == 422, "X-Step-Up-Token is required"

    token = await _token_by_password(client, headers, StepUpScope.UNLINK_PASSKEY)
    with_token = await client.delete(
        f"/api/auth/passkey/{cred_id}",
        headers={**headers, "X-Step-Up-Token": token},
    )
    assert with_token.status_code == 204


async def test_the_grant_never_travels_in_the_url(client, session_maker):
    """A query string ends up in nginx access logs, browser history and
    `Referer`. Passing the grant there must not work, or the header would be
    advisory rather than required."""
    _, headers = await _account(client, "su-url")
    me = await client.get("/api/auth/me", headers=headers)
    uid = uuid.UUID(me.json()["id"])

    async with session_maker() as db:
        cred = WebAuthnCredential(
            user_id=uid, credential_id=uuid.uuid4().bytes, public_key=b"pk"
        )
        db.add(cred)
        await db.commit()
        await db.refresh(cred)
        cred_id = cred.id

    token = await _token_by_password(client, headers, StepUpScope.UNLINK_PASSKEY)
    resp = await client.delete(
        f"/api/auth/passkey/{cred_id}?step_up_token={token}", headers=headers
    )
    assert resp.status_code == 422
