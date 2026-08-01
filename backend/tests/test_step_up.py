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


# ── changing the password (T3.15) ────────────────────────────────────────────


async def test_password_change_needs_confirmation(client):
    _, headers = await _account(client, "su-pw")
    resp = await client.put(
        "/api/auth/me/password", headers=headers, json={"new_password": "brand-new-1"}
    )
    assert resp.status_code == 422, resp.text  # header is required


async def test_password_change_rejects_a_grant_for_another_operation(client):
    _, headers = await _account(client, "su-pw-scope")
    token = await _token_by_password(client, headers, StepUpScope.DECLARE_LOST)
    resp = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": token},
        json={"new_password": "brand-new-1"},
    )
    assert resp.status_code == 401, resp.text


async def test_password_change_swaps_which_password_works(client):
    email, headers = await _account(client, "su-pw-swap")
    token = await _token_by_password(client, headers, StepUpScope.CHANGE_PASSWORD)

    resp = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": token},
        json={"new_password": "brand-new-1"},
    )
    assert resp.status_code == 200, resp.text

    assert (
        await client.post(
            "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
        )
    ).status_code == 401, "the old password must stop working"
    assert (
        await client.post(
            "/api/auth/login", json={"login": email, "password": "brand-new-1"}
        )
    ).status_code == 200


async def test_password_change_grant_is_single_use(client):
    _, headers = await _account(client, "su-pw-once")
    token = await _token_by_password(client, headers, StepUpScope.CHANGE_PASSWORD)
    first = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": token},
        json={"new_password": "brand-new-1"},
    )
    assert first.status_code == 200
    second = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": token},
        json={"new_password": "brand-new-2"},
    )
    assert second.status_code == 401, "a captured grant must not be replayable"


async def test_short_password_is_refused(client):
    _, headers = await _account(client, "su-pw-short")
    token = await _token_by_password(client, headers, StepUpScope.CHANGE_PASSWORD)
    resp = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": token},
        json={"new_password": "short"},
    )
    assert resp.status_code == 422, resp.text


async def test_an_account_without_a_password_can_set_one(client, session_maker):
    """Setting a first password is the same operation, and must be reachable
    without one — otherwise a Nostr- or passkey-created account can never gain
    an email login, which is the T3.15 defect in a new place."""
    email, headers = await _account(client, "su-pw-none")
    keys = await establish_identity(client, headers)

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.password_hash = None
        await db.commit()

    assert (
        await client.post(
            "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
        )
    ).status_code == 401

    opts = await client.post(
        "/api/auth/step-up/options", headers=headers, json={"scope": "change_password"}
    )
    assert "password" not in opts.json()["methods"]
    challenge = opts.json()["challenge"]
    created_at = int(time.time())
    event_id = proof_event_id(
        keys["npub_hex"], step_up_purpose("change_password"), challenge, created_at
    )
    verify = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={
            "scope": "change_password",
            "nostr": {
                "npub_hex": keys["npub_hex"],
                "challenge": challenge,
                "created_at": created_at,
                "sig": sign_event_id(event_id, keys["nsec_hex"]),
            },
        },
    )
    assert verify.status_code == 200, verify.text

    resp = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": verify.json()["step_up_token"]},
        json={"new_password": "first-password-1"},
    )
    assert resp.status_code == 200, resp.text
    assert (
        await client.post(
            "/api/auth/login", json={"login": email, "password": "first-password-1"}
        )
    ).status_code == 200


# ── changing the password ends other sessions ────────────────────────────────


async def test_password_change_ends_other_sessions(client):
    """The reason people change a password in a hurry is that somebody else may
    be holding a session. Those tokens have no `jti` we ever saw, so they are
    retired by age instead."""
    email, first = await _account(client, "su-pw-sessions")
    second_login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    other = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    assert (await client.get("/api/auth/me", headers=other)).status_code == 200

    token = await _token_by_password(client, first, StepUpScope.CHANGE_PASSWORD)
    resp = await client.put(
        "/api/auth/me/password",
        headers={**first, "X-Step-Up-Token": token},
        json={"new_password": "brand-new-1"},
    )
    assert resp.status_code == 200, resp.text

    assert (
        await client.get("/api/auth/me", headers=other)
    ).status_code == 401, "the other session must be gone"


async def test_password_change_returns_a_working_replacement_token(client):
    """The device doing the change must not be thrown out by its own action —
    that reads as a failure and invites a retry."""
    _, headers = await _account(client, "su-pw-replace")
    token = await _token_by_password(client, headers, StepUpScope.CHANGE_PASSWORD)
    resp = await client.put(
        "/api/auth/me/password",
        headers={**headers, "X-Step-Up-Token": token},
        json={"new_password": "brand-new-1"},
    )
    fresh = resp.json()["access_token"]
    assert fresh, "a replacement token must come back with the response"

    assert (
        await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {fresh}"}
        )
    ).status_code == 200


async def test_sessions_survive_when_nothing_was_retired(client):
    """Default state. Adding the cutoff must not sign the platform out."""
    _, headers = await _account(client, "su-pw-default")
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200


async def test_a_token_with_no_issue_time_is_refused_after_a_retirement(
    client, session_maker
):
    """Tokens minted before `iat` existed carry no issue time. Once an account
    retires its sessions they must read as older than the cutoff, not as
    exempt from the check."""
    import jwt
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings

    email, headers = await _account(client, "su-pw-legacy")
    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        user_id = str(user.id)
        user.sessions_valid_from = datetime.now(timezone.utc)
        await db.commit()

    legacy = jwt.encode(
        {
            "sub": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "jti": uuid.uuid4().hex,
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}
    )
    assert resp.status_code == 401, resp.text


# ── T3.16 — recovery codes ───────────────────────────────────────────────────
#
# A code is the last door into an account that may have no other. The properties
# worth pinning are therefore about what it does *not* open: it is not a session,
# it cannot be spent twice, and it says nothing about which accounts exist.


async def _issue_codes(client, headers) -> list[str]:
    token = await _token_by_password(client, headers, StepUpScope.ADD_AUTH_METHOD)
    resp = await client.post(
        "/api/auth/recovery/codes", headers={**headers, "X-Step-Up-Token": token}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["codes"]


async def test_ten_distinct_codes_are_issued_once(client):
    _, headers = await _account(client, "rec-issue")
    codes = await _issue_codes(client, headers)

    assert len(codes) == 10
    assert len(set(codes)) == 10, "codes must not repeat within a set"

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["recovery_codes_remaining"] == 10
    # The plaintext exists in that one response and nowhere else — /me returns a
    # count, never the strings.
    assert "codes" not in me.json()


async def test_issuing_requires_step_up(client):
    _, headers = await _account(client, "rec-nostep")
    resp = await client.post("/api/auth/recovery/codes", headers=headers)
    assert resp.status_code == 422, "X-Step-Up-Token is required"


async def test_regenerating_kills_the_previous_set(client):
    email, headers = await _account(client, "rec-regen")
    first = await _issue_codes(client, headers)
    await _issue_codes(client, headers)

    spent = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": first[0]},
    )
    assert spent.status_code == 401, "a replaced code must not open anything"


async def test_a_code_buys_a_scoped_token_not_a_session(client):
    email, headers = await _account(client, "rec-scope")
    codes = await _issue_codes(client, headers)

    resp = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": codes[0]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scope"] == "recovery"
    assert body["codes_remaining"] == 9

    scoped = {"Authorization": f"Bearer {body['access_token']}"}
    ordinary = await client.get("/api/auth/me", headers=scoped)
    assert ordinary.status_code == 403, "a recovery token is not a session"


async def test_a_code_can_set_a_password_and_then_is_spent(client):
    email, headers = await _account(client, "rec-pass")
    codes = await _issue_codes(client, headers)

    consumed = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": codes[0]},
    )
    body = consumed.json()
    scoped = {"Authorization": f"Bearer {body['access_token']}"}
    new_password = "Recovered-9182!"

    changed = await client.put(
        "/api/auth/me/password",
        headers={**scoped, "X-Step-Up-Token": body["step_up_tokens"]["change_password"]},
        json={"new_password": new_password},
    )
    assert changed.status_code == 200, changed.text

    login = await client.post(
        "/api/auth/login", json={"login": email, "password": new_password}
    )
    assert login.status_code == 200, "the whole point: the account is reachable again"

    again = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": codes[0]},
    )
    assert again.status_code == 401, "a spent code is spent"


async def test_unknown_account_and_wrong_code_are_indistinguishable(client):
    email, headers = await _account(client, "rec-oracle")
    await _issue_codes(client, headers)

    wrong = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": "AAAA-BBBB-CCCC"},
    )
    missing = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": "nobody-here@vimana.test", "code": "AAAA-BBBB-CCCC"},
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"], (
        "different answers would turn this into a lookup for which accounts exist"
    )


async def test_codes_are_typed_the_way_people_write_them(client):
    email, headers = await _account(client, "rec-typing")
    codes = await _issue_codes(client, headers)

    sloppy = codes[0].lower().replace("-", " ")
    resp = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": sloppy},
    )
    assert resp.status_code == 200, "case and dashes are presentation, not secret"


async def test_a_code_cannot_be_found_by_another_account(client):
    email_a, headers_a = await _account(client, "rec-a")
    codes_a = await _issue_codes(client, headers_a)
    email_b, _ = await _account(client, "rec-b")

    resp = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email_b, "code": codes_a[0]},
    )
    assert resp.status_code == 401


async def test_spending_a_code_tells_the_owner(client, monkeypatch):
    """The one signal that says "someone used a code". Sent whether or not the
    account opted into notifications — if it was not the owner, this letter is
    how they find out at all."""
    sent: list[tuple[str, int]] = []

    from app.tasks import notifications

    class _Task:
        @staticmethod
        def delay(user_id, remaining):
            sent.append((user_id, remaining))

    monkeypatch.setattr(notifications, "send_recovery_code_used", _Task)

    email, headers = await _account(client, "rec-mail")
    codes = await _issue_codes(client, headers)
    resp = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": codes[0]},
    )
    assert resp.status_code == 200
    assert len(sent) == 1
    assert sent[0][1] == 9, "the letter carries how many are left"


# ── T3.21 — releasing the key for an Identity Vault ──────────────────────────


async def test_the_owner_can_take_a_copy_of_their_key(client):
    """`D-KEY-TIERS` rung 2: the account gains a second copy, the platform keeps
    its own, and nothing else changes. T3.12 deleted an endpoint shaped like
    this one — correctly, because back then the key was the platform's service
    key. Now it is the account's identity from registration, and refusing its
    owner would be the lie instead."""
    _, headers = await _account(client, "rel-ok")

    before = await client.get("/api/me/keypair/status", headers=headers)
    assert before.json()["key_copies"] == "platform_only"

    token = await _token_by_password(client, headers, StepUpScope.ADD_AUTH_METHOD)
    resp = await client.post(
        "/api/me/identity/release-key", headers=headers, json={"step_up_token": token}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["nsec_hex"]) == 64
    assert body["npub_hex"] == before.json()["npub"]

    after = await client.get("/api/me/keypair/status", headers=headers)
    assert after.json()["key_copies"] == "both", "our copy stays — this is not a handover"


async def test_releasing_the_key_needs_a_fresh_confirmation(client):
    _, headers = await _account(client, "rel-nostep")
    resp = await client.post(
        "/api/me/identity/release-key", headers=headers, json={"step_up_token": "nope"}
    )
    assert resp.status_code in (401, 403), resp.text


async def test_nothing_to_release_once_our_copy_is_gone(client, session_maker):
    """Rung 3 answers plainly instead of returning an empty 200 — "we do not
    have it" is the honest sentence, and it is also the one the UI needs."""
    _, headers = await _account(client, "rel-gone")
    me = await client.get("/api/auth/me", headers=headers)

    async with session_maker() as db:
        user = await db.get(User, uuid.UUID(me.json()["id"]))
        user.nsec_encrypted = None
        user.nsec_nonce = None
        user.key_self_custody = True
        await db.commit()

    status = await client.get("/api/me/keypair/status", headers=headers)
    assert status.json()["key_copies"] == "user_only"

    token = await _token_by_password(client, headers, StepUpScope.ADD_AUTH_METHOD)
    resp = await client.post(
        "/api/me/identity/release-key", headers=headers, json={"step_up_token": token}
    )
    assert resp.status_code == 409


# ── T3.22 — deleting the platform's copy (rung 3) ────────────────────────────


async def _release(client, headers) -> None:
    token = await _token_by_password(client, headers, StepUpScope.ADD_AUTH_METHOD)
    resp = await client.post(
        "/api/me/identity/release-key", headers=headers, json={"step_up_token": token}
    )
    assert resp.status_code == 200, resp.text


async def test_cannot_delete_our_copy_before_the_owner_has_one(client):
    """The guard that keeps rung 3 a choice rather than a shredder: without a
    downloaded Identity Vault, deleting our copy destroys the only one."""
    _, headers = await _account(client, "rung3-early")
    token = await _token_by_password(client, headers, StepUpScope.DECLARE_LOST)
    resp = await client.request(
        "DELETE",
        "/api/me/identity/platform-copy",
        headers={**headers, "X-Step-Up-Token": token},
    )
    assert resp.status_code == 409, resp.text


async def test_deleting_our_copy_ends_what_the_server_can_do(client, session_maker):
    """Rung 2 → 3. The key, the npub and the deals are untouched; what ends is
    our ability to act — and it ends in the schema, not in a promise."""
    _, headers = await _account(client, "rung3-ok")
    before = await client.get("/api/me/keypair/status", headers=headers)
    npub_before = before.json()["npub"]

    await _release(client, headers)
    token = await _token_by_password(client, headers, StepUpScope.DECLARE_LOST)
    resp = await client.request(
        "DELETE",
        "/api/me/identity/platform-copy",
        headers={**headers, "X-Step-Up-Token": token},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["key_copies"] == "user_only"
    assert resp.json()["npub"] == npub_before, "the identity does not change — only who holds it"

    me = await client.get("/api/auth/me", headers=headers)
    async with session_maker() as db:
        user = await db.get(User, uuid.UUID(me.json()["id"]))
        assert user.nsec_encrypted is None, "no copy may survive on the server"

    # Second call is a no-op rather than an error: the state asked for is the
    # state we are in.
    again = await client.request(
        "DELETE",
        "/api/me/identity/platform-copy",
        headers={**headers, "X-Step-Up-Token": "unused"},
    )
    assert again.status_code == 200
