"""T3.11 — email confirmation by code.

Confirming gates nothing (owner's decision 2026-07-26) — the tests at the
bottom pin that down, because a "verify your email" feature quietly growing
back into a permission check is exactly the kind of drift nobody notices.

Registrations here deliberately use a domain that is NOT in
`E2E_AUTO_VERIFY_EMAIL_DOMAINS` (conftest sets `vimana.test` and
`e2e.vimana.local`), so the real code exchange runs instead of the bypass.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.email_verification import MAX_ATTEMPTS
from app.core.security import create_access_token
from app.models.user import User

PASSWORD = "verify-password-1"
FIXED_CODE = "424242"


def gated_email(prefix: str = "verify") -> str:
    """Domain outside the auto-verify list — the real flow applies."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@verify.test"


@pytest.fixture
def fixed_code(monkeypatch):
    """Pin the generated code so tests can present it back."""
    from app.core import email_verification as ev

    monkeypatch.setattr(ev, "generate_code", lambda: FIXED_CODE)
    return FIXED_CODE


@pytest.fixture
def captured_codes(monkeypatch):
    """Intercept the Celery hand-off; returns the list it appends to."""
    sent: list[tuple[str, str]] = []
    from app.tasks import notifications

    class _Capture:
        def delay(self, user_id, code):
            sent.append((user_id, code))

    monkeypatch.setattr(notifications, "send_verification_code", _Capture())
    return sent


async def _register(client, email: str, **extra) -> dict:
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Verify User",
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _headers(client, email: str) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/login", json={"login": email, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _fetch(session_maker, email: str) -> User:
    async with session_maker() as db:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one()


# ── registration → code issued ───────────────────────────────────────────────


async def test_register_leaves_email_unverified(client, fixed_code, captured_codes):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email_verified"] is False


async def test_register_dispatches_code_to_celery(client, fixed_code, captured_codes):
    email = gated_email()
    await _register(client, email)
    assert len(captured_codes) == 1
    assert captured_codes[0][1] == FIXED_CODE


async def test_code_is_stored_hashed(client, fixed_code, captured_codes, session_maker):
    email = gated_email()
    await _register(client, email)
    user = await _fetch(session_maker, email)
    assert user.email_verification_code_hash
    assert FIXED_CODE not in user.email_verification_code_hash
    assert user.email_verification_code_hash.startswith("$2b$")


async def test_login_works_while_unverified(client, fixed_code, captured_codes):
    """The gate is soft — an unproven address never blocks sign-in."""
    email = gated_email()
    await _register(client, email)
    await _headers(client, email)  # raises if login fails


# ── verify ───────────────────────────────────────────────────────────────────


async def test_verify_with_correct_code(client, fixed_code, captured_codes):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["email_verified"] is True


async def test_verify_clears_pending_code(
    client, fixed_code, captured_codes, session_maker
):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)
    await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )

    user = await _fetch(session_maker, email)
    assert user.email_verification_code_hash is None
    assert user.email_verification_expires_at is None
    assert user.email_verification_attempts == 0


async def test_verify_wrong_code(client, fixed_code, captured_codes, session_maker):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": "000000"}
    )
    assert resp.status_code == 400

    user = await _fetch(session_maker, email)
    assert user.email_verification_attempts == 1
    assert user.email_verified_at is None


async def test_verify_expired_code(client, fixed_code, captured_codes, session_maker):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    async with session_maker() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.email_verification_expires_at = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        await db.commit()

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


async def test_attempt_cap_burns_the_code(
    client, fixed_code, captured_codes, session_maker
):
    """Hitting the cap must invalidate the code outright — a cap that only
    refuses the current guess slows an attacker down, it does not stop them."""
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    for _ in range(MAX_ATTEMPTS - 1):
        resp = await client.post(
            "/api/auth/email/verify", headers=headers, json={"code": "000000"}
        )
        assert resp.status_code == 400

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": "000000"}
    )
    assert resp.status_code == 429

    user = await _fetch(session_maker, email)
    assert user.email_verification_code_hash is None

    # The real code no longer works either — it was burned with the budget.
    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 400


async def test_verify_is_idempotent(client, fixed_code, captured_codes):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)
    await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_verified"


# ── request-code ─────────────────────────────────────────────────────────────


async def test_request_code_cooldown(client, fixed_code, captured_codes):
    email = gated_email()
    await _register(client, email)  # registration already sent one
    headers = await _headers(client, email)

    resp = await client.post("/api/auth/email/request-code", headers=headers)
    assert resp.status_code == 429


async def test_request_code_after_cooldown_resets_attempts(
    client, fixed_code, captured_codes, session_maker
):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": "000000"}
    )

    async with session_maker() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.email_verification_sent_at = datetime.now(timezone.utc) - timedelta(
            minutes=5
        )
        await db.commit()

    resp = await client.post("/api/auth/email/request-code", headers=headers)
    assert resp.status_code == 202

    user = await _fetch(session_maker, email)
    assert user.email_verification_attempts == 0


async def test_request_code_when_already_verified(client, fixed_code, captured_codes):
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)
    await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )

    resp = await client.post("/api/auth/email/request-code", headers=headers)
    assert resp.status_code == 202
    assert resp.json()["status"] == "already_verified"


async def test_request_code_without_email(client, session_maker):
    """T3.13/T3.14 accounts have no address to prove — 422, not a silent send."""
    async with session_maker() as db:
        user = User(
            email=None,
            password_hash=None,
            display_name="Keyless",
            can_carry=True,
            can_send=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = str(user.id)

    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    resp = await client.post("/api/auth/email/request-code", headers=headers)
    assert resp.status_code == 422


# ── verification gates nothing (owner's decision 2026-07-26) ─────────────────


async def _trip_body() -> dict:
    return {
        "origin": "Tbilisi",
        "destination": "Yerevan",
        "depart_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "capacity": 5.0,
        "allowed_categories": ["documents"],
    }


async def test_unverified_user_can_publish_a_trip(client, fixed_code, captured_codes):
    """An unproven address is a security question, not a capability one — it
    must not cost the user anything they could otherwise do."""
    email = gated_email()
    await _register(client, email, can_carry=True)
    headers = await _headers(client, email)

    resp = await client.post("/api/trips", headers=headers, json=await _trip_body())
    assert resp.status_code == 201


async def test_unverified_user_can_start_a_deal(client, fixed_code, captured_codes):
    """404 for the made-up trip id — the point is that it is not a 403."""
    email = gated_email()
    await _register(client, email)
    headers = await _headers(client, email)

    resp = await client.post(
        "/api/deals/match",
        headers=headers,
        json={
            "trip_id": str(uuid.uuid4()),
            "order": {
                "recipient_contact": "someone@verify.test",
                "origin": "Tbilisi",
                "destination": "Yerevan",
                "category": "documents",
                "declared_value": 10.0,
            },
        },
    )
    assert resp.status_code == 404


async def test_account_without_email_works_normally(client, session_maker):
    """T3.13/T3.14 accounts never claim an address and must not be nagged or
    limited anywhere."""
    async with session_maker() as db:
        user = User(
            email=None,
            password_hash=None,
            display_name="Keyless Carrier",
            can_carry=True,
            can_send=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = str(user.id)

    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    resp = await client.post("/api/trips", headers=headers, json=await _trip_body())
    assert resp.status_code == 201


# ── e2e bypass ───────────────────────────────────────────────────────────────


async def test_auto_verify_domain_skips_the_flow(client, captured_codes):
    """`vimana.test` is in the auto-verify list (conftest) — no code is sent."""
    email = f"auto-{uuid.uuid4().hex[:8]}@vimana.test"
    await _register(client, email)
    headers = await _headers(client, email)

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["email_verified"] is True
    assert captured_codes == []


# ── changing the address (T3.15) ─────────────────────────────────────────────
#
# The property under test: the current address keeps working, verified, until
# the new one is proven. Everything below is a consequence of that — a typo is
# recoverable, a stolen session cannot silently redirect recovery mail, and a
# race for the same address is decided by whoever confirms first.


async def _step_up(client, headers, scope: str = "change_email") -> str:
    resp = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={"scope": scope, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["step_up_token"]


async def _verified_account(client, fixed_code, captured_codes) -> tuple[str, dict]:
    """Register and confirm, so tests start from a proven address."""
    email = gated_email("change")
    await _register(client, email)
    headers = await _headers(client, email)
    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 200, resp.text
    captured_codes.clear()
    return email, headers


async def test_change_requires_step_up(client, fixed_code, captured_codes):
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    resp = await client.post(
        "/api/auth/email/change", headers=headers, json={"email": gated_email("new")}
    )
    # Missing required header — FastAPI rejects before the handler runs.
    assert resp.status_code == 422, resp.text


async def test_change_rejects_a_grant_for_another_operation(
    client, fixed_code, captured_codes
):
    """The whole point of scoping: confirming one thing must not authorise
    another."""
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    token = await _step_up(client, headers, scope="declare_lost")
    resp = await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": gated_email("new")},
    )
    assert resp.status_code == 401, resp.text


async def test_change_leaves_the_current_address_live_until_proven(
    client, fixed_code, captured_codes, session_maker
):
    old, headers = await _verified_account(client, fixed_code, captured_codes)
    new = gated_email("new")
    token = await _step_up(client, headers)

    resp = await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": new},
    )
    assert resp.status_code == 202, resp.text

    user = await _fetch(session_maker, old)
    assert user.email == old, "the address must not move before it is proven"
    assert user.pending_email == new
    assert user.email_verified_at is not None, "the old address stays verified"

    # And it still signs in — the recovery channel is unbroken meanwhile.
    assert (
        await client.post(
            "/api/auth/login", json={"login": old, "password": PASSWORD}
        )
    ).status_code == 200


async def test_code_goes_to_the_new_address(
    client, fixed_code, captured_codes, session_maker
):
    """Delivery target, not just storage: asking the old mailbox to vouch for
    the new one would prove nothing about the new one."""
    from app.core.email_verification import target_email

    old, headers = await _verified_account(client, fixed_code, captured_codes)
    new = gated_email("new")
    token = await _step_up(client, headers)
    await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": new},
    )

    assert len(captured_codes) == 1, "a change must mint a code"
    user = await _fetch(session_maker, old)
    assert target_email(user) == new


async def test_confirming_moves_the_address(
    client, fixed_code, captured_codes, session_maker
):
    old, headers = await _verified_account(client, fixed_code, captured_codes)
    new = gated_email("new")
    token = await _step_up(client, headers)
    await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": new},
    )

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "changed"
    assert resp.json()["email"] == new

    user = await _fetch(session_maker, new)
    assert user.pending_email is None
    assert user.email_verified_at is not None

    assert (
        await client.post(
            "/api/auth/login", json={"login": new, "password": PASSWORD}
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/auth/login", json={"login": old, "password": PASSWORD}
        )
    ).status_code == 401


async def test_a_change_can_be_confirmed_even_though_the_old_address_was_verified(
    client, fixed_code, captured_codes
):
    """Regression guard: the verify and request-code endpoints short-circuit on
    `email_verified_at`, which would leave a started change with no way to
    finish."""
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    token = await _step_up(client, headers)
    await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": gated_email("new")},
    )

    resend = await client.post("/api/auth/email/request-code", headers=headers)
    assert resend.status_code in (202, 429), resend.text
    assert resend.json().get("status") != "already_verified"


async def test_cancelling_restores_the_previous_state(
    client, fixed_code, captured_codes, session_maker
):
    old, headers = await _verified_account(client, fixed_code, captured_codes)
    token = await _step_up(client, headers)
    await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": gated_email("new")},
    )

    resp = await client.delete("/api/auth/email/pending", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    user = await _fetch(session_maker, old)
    assert user.pending_email is None
    # The outstanding code died with the claim: alive, it could later settle a
    # question about the current address instead.
    assert user.email_verification_code_hash is None


async def test_cancelling_nothing_is_not_an_error(client, fixed_code, captured_codes):
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    resp = await client.delete("/api/auth/email/pending", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "nothing_pending"


async def test_cannot_move_to_a_registered_address(
    client, fixed_code, captured_codes
):
    taken = gated_email("taken")
    await _register(client, taken)
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    token = await _step_up(client, headers)

    resp = await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": taken},
    )
    assert resp.status_code == 409, resp.text


async def test_cannot_move_to_the_current_address(client, fixed_code, captured_codes):
    old, headers = await _verified_account(client, fixed_code, captured_codes)
    token = await _step_up(client, headers)
    resp = await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": old},
    )
    assert resp.status_code == 409, resp.text


async def test_malformed_address_is_refused(client, fixed_code, captured_codes):
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    token = await _step_up(client, headers)
    resp = await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": "not-an-address"},
    )
    assert resp.status_code == 422, resp.text


async def test_losing_the_race_leaves_the_account_with_a_working_address(
    client, fixed_code, captured_codes, session_maker
):
    """A pending claim reserves nothing. If someone registers the address while
    the change is in flight, confirming fails — and must fail *without*
    stranding the account."""
    old, headers = await _verified_account(client, fixed_code, captured_codes)
    contested = gated_email("contested")
    token = await _step_up(client, headers)
    await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": contested},
    )

    await _register(client, contested)  # someone else got there first

    resp = await client.post(
        "/api/auth/email/verify", headers=headers, json={"code": FIXED_CODE}
    )
    assert resp.status_code == 409, resp.text

    user = await _fetch(session_maker, old)
    assert user.email == old
    assert user.email_verified_at is not None


async def test_me_exposes_the_pending_address(client, fixed_code, captured_codes):
    _, headers = await _verified_account(client, fixed_code, captured_codes)
    new = gated_email("new")
    token = await _step_up(client, headers)
    await client.post(
        "/api/auth/email/change",
        headers={**headers, "X-Step-Up-Token": token},
        json={"email": new},
    )

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["pending_email"] == new
    assert me.json()["has_password"] is True
