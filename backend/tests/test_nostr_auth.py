"""T3.13 — signing in and signing up with a Nostr key.

The property under test throughout: possession of the private key, proven over
a challenge the server issued, and nothing else. No password, no email, no
trust in what the client asserts about itself.
"""
import time
import uuid

from sqlalchemy import select

from app.core.identity_proof import (
    PURPOSE_ESTABLISH,
    PURPOSE_LOGIN,
    PURPOSE_SIGNUP,
    proof_event_id,
)
from app.core.keypair import generate_keypair, sign_event_id
from app.models.user import User
from tests.conftest import SEED_PASSWORD, unique_email


def _sign(npub, nsec, challenge, purpose, created_at=None) -> dict:
    created_at = created_at if created_at is not None else int(time.time())
    event_id = proof_event_id(npub, purpose, challenge, created_at)
    return {
        "npub_hex": npub,
        "challenge": challenge,
        "created_at": created_at,
        "sig": sign_event_id(event_id, nsec),
    }


async def _challenge(client, npub: str) -> str:
    resp = await client.post(
        "/api/auth/nostr/challenge", json={"pubkey_hex": npub}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["challenge"]


async def _signup(client, *, display_name="Nostrian", email=None) -> tuple[str, str, dict]:
    nsec, npub = generate_keypair()
    challenge = await _challenge(client, npub)
    payload = _sign(npub, nsec, challenge, PURPOSE_SIGNUP)
    payload["display_name"] = display_name
    if email:
        payload["email"] = email
    resp = await client.post("/api/auth/nostr/signup", json=payload)
    return nsec, npub, resp


# ── challenge ────────────────────────────────────────────────────────────────


async def test_challenge_is_public(client):
    """Issued for any pubkey on request. Refusing unknown ones would turn this
    into an oracle for which keys have accounts, and a challenge is worthless
    without the private key anyway."""
    _, npub = generate_keypair()
    resp = await client.post(
        "/api/auth/nostr/challenge", json={"pubkey_hex": npub}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["challenge"]) == 64
    assert body["purpose_login"] == PURPOSE_LOGIN
    assert body["purpose_signup"] == PURPOSE_SIGNUP


async def test_challenge_rejects_malformed_pubkey(client):
    resp = await client.post(
        "/api/auth/nostr/challenge", json={"pubkey_hex": "nope"}
    )
    assert resp.status_code == 422


# ── signup ───────────────────────────────────────────────────────────────────


async def test_signup_creates_a_self_custody_account(client, session_maker):
    nsec, npub, resp = await _signup(client)
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["user"]["nostr_pubkey"] == npub
    assert body["token"]["access_token"]

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.nostr_pubkey == npub))
        ).scalar_one()
    # Self-custody from birth: the platform never held a key for this account.
    assert user.key_self_custody is True
    assert user.nsec_encrypted is None
    assert user.password_hash is None
    assert user.email is None


async def test_signup_token_works_immediately(client):
    """There is no password to log in with afterwards, so signup must hand back
    a usable session or the account is unreachable."""
    _, npub, resp = await _signup(client)
    token = resp.json()["token"]["access_token"]

    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["nostr_pubkey"] == npub


async def test_signup_rejects_a_bad_signature(client):
    _, npub = generate_keypair()
    other_nsec, _ = generate_keypair()
    challenge = await _challenge(client, npub)

    payload = _sign(npub, other_nsec, challenge, PURPOSE_SIGNUP)
    payload["display_name"] = "Impostor"
    resp = await client.post("/api/auth/nostr/signup", json=payload)
    assert resp.status_code == 401


async def test_signup_refuses_a_key_that_already_has_an_account(client):
    nsec, npub, first = await _signup(client)
    assert first.status_code == 201

    challenge = await _challenge(client, npub)
    payload = _sign(npub, nsec, challenge, PURPOSE_SIGNUP)
    payload["display_name"] = "Twice"
    resp = await client.post("/api/auth/nostr/signup", json=payload)
    assert resp.status_code == 409


async def test_signup_with_email_starts_verification(client, session_maker):
    email = f"nostr-{uuid.uuid4().hex[:8]}@verify.test"
    _, npub, resp = await _signup(client, email=email)
    assert resp.status_code == 201

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.nostr_pubkey == npub))
        ).scalar_one()
    assert user.email == email
    assert user.email_verified_at is None
    assert user.email_verification_code_hash is not None


# ── login ────────────────────────────────────────────────────────────────────


async def test_login_with_the_key(client):
    nsec, npub, _ = await _signup(client)

    challenge = await _challenge(client, npub)
    resp = await client.post(
        "/api/auth/nostr/verify", json=_sign(npub, nsec, challenge, PURPOSE_LOGIN)
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.json()["nostr_pubkey"] == npub


async def test_unknown_key_is_404_not_401(client):
    """The client has to tell 'not registered — offer signup' apart from 'your
    signature is wrong'. And no account is created here: a valid signature
    proves key ownership, not intent to join."""
    nsec, npub = generate_keypair()
    challenge = await _challenge(client, npub)

    resp = await client.post(
        "/api/auth/nostr/verify", json=_sign(npub, nsec, challenge, PURPOSE_LOGIN)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "nostr_pubkey_unknown"


async def test_login_rejects_signature_from_another_key(client):
    _, npub, _ = await _signup(client)
    other_nsec, _ = generate_keypair()

    challenge = await _challenge(client, npub)
    resp = await client.post(
        "/api/auth/nostr/verify",
        json=_sign(npub, other_nsec, challenge, PURPOSE_LOGIN),
    )
    assert resp.status_code == 401


async def test_challenge_is_single_use(client):
    nsec, npub, _ = await _signup(client)
    challenge = await _challenge(client, npub)
    payload = _sign(npub, nsec, challenge, PURPOSE_LOGIN)

    first = await client.post("/api/auth/nostr/verify", json=payload)
    assert first.status_code == 200

    replay = await client.post("/api/auth/nostr/verify", json=payload)
    assert replay.status_code == 401


async def test_stale_timestamp_rejected(client):
    nsec, npub, _ = await _signup(client)
    challenge = await _challenge(client, npub)

    resp = await client.post(
        "/api/auth/nostr/verify",
        json=_sign(
            npub, nsec, challenge, PURPOSE_LOGIN, created_at=int(time.time()) - 3600
        ),
    )
    assert resp.status_code == 401


async def test_a_login_proof_cannot_create_an_account(client):
    """Purposes are inside the signed payload precisely so a signature
    collected for one flow is worthless in another."""
    nsec, npub = generate_keypair()
    challenge = await _challenge(client, npub)

    payload = _sign(npub, nsec, challenge, PURPOSE_LOGIN)
    payload["display_name"] = "Sneaky"
    resp = await client.post("/api/auth/nostr/signup", json=payload)
    assert resp.status_code == 401


async def test_an_establish_proof_cannot_log_in(client):
    nsec, npub, _ = await _signup(client)
    challenge = await _challenge(client, npub)

    resp = await client.post(
        "/api/auth/nostr/verify",
        json=_sign(npub, nsec, challenge, PURPOSE_ESTABLISH),
    )
    assert resp.status_code == 401


async def test_retired_identity_cannot_log_in(client, session_maker):
    """`declare-lost` (T3.12) is terminal — the key may still sign, but the
    account it points at is out of service."""
    from datetime import datetime, timezone

    nsec, npub, _ = await _signup(client)
    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.nostr_pubkey == npub))
        ).scalar_one()
        user.key_lost_at = datetime.now(timezone.utc)
        await db.commit()

    challenge = await _challenge(client, npub)
    resp = await client.post(
        "/api/auth/nostr/verify", json=_sign(npub, nsec, challenge, PURPOSE_LOGIN)
    )
    assert resp.status_code == 403


async def test_password_login_still_untouched(client, seed_sender):
    """The email+password path keeps working — Nostr login is an addition, not
    a replacement."""
    resp = await client.post(
        "/api/auth/login",
        json={"login": seed_sender.email, "password": SEED_PASSWORD},
    )
    assert resp.status_code == 200


async def test_nostr_account_cannot_use_the_password_route(client):
    """No password means no password login, and the route must say 401 rather
    than crash on a NULL hash."""
    _, npub, resp = await _signup(client)
    assert resp.status_code == 201

    login = await client.post(
        "/api/auth/login",
        json={"login": unique_email("ghost"), "password": "whatever"},
    )
    assert login.status_code == 401
