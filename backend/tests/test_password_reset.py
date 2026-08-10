"""T_SEC.5 — the way back for an account that has a password and forgot it."""
import uuid as uuidlib

import pytest

from tests.test_notifications import sync_test_session  # noqa: F401

from tests.conftest import SEED_PASSWORD, unique_email


async def _register(client, email: str, *, password: str = SEED_PASSWORD):
    return await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": email[:8]},
    )


@pytest.fixture
def queued_reset(monkeypatch):
    """Capture the dispatch rather than the letter: the plaintext token exists
    only as an argument, which is the property worth asserting."""
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(
        notif.send_password_reset, "delay", lambda uid, token: sent.append((uid, token))
    )
    return sent


async def test_forgot_answers_202_for_an_unknown_address(client, queued_reset):
    """A public form must not become a directory of who banks here."""
    resp = await client.post(
        "/api/auth/password/forgot", json={"identifier": "nobody@vimana.test"}
    )
    assert resp.status_code == 202
    assert queued_reset == []


async def test_forgot_answers_202_for_a_known_address(client, queued_reset):
    email = unique_email("reset-known")
    await _register(client, email)
    resp = await client.post("/api/auth/password/forgot", json={"identifier": email})
    assert resp.status_code == 202


async def test_forgot_sends_only_to_a_verified_address(client, queued_reset, session_maker):
    """A reset link is the account; an unproven mailbox must not receive one."""
    from sqlalchemy import select

    from app.models.user import User

    email = f"reset-unver-{uuidlib.uuid4().hex[:8]}@notverified.test"
    await _register(client, email)

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert user.email_verified_at is None, "domain must be outside auto-verify"

    resp = await client.post("/api/auth/password/forgot", json={"identifier": email})
    assert resp.status_code == 202, "the answer stays the same"
    assert queued_reset == [], "but nothing is sent"


async def test_reset_sets_the_new_password_and_signs_in(client, queued_reset):
    email = unique_email("reset-ok")
    await _register(client, email)
    await client.post("/api/auth/password/forgot", json={"identifier": email})
    assert len(queued_reset) == 1
    _, token = queued_reset[0]

    resp = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "brand-new-pw-1"}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    old = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    assert old.status_code == 401, "the old password must stop working"
    new = await client.post(
        "/api/auth/login", json={"login": email, "password": "brand-new-pw-1"}
    )
    assert new.status_code == 200


async def test_a_token_works_once(client, queued_reset):
    email = unique_email("reset-once")
    await _register(client, email)
    await client.post("/api/auth/password/forgot", json={"identifier": email})
    _, token = queued_reset[0]

    first = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "first-pw-12345"}
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "second-pw-1234"}
    )
    assert second.status_code == 400


async def test_a_wrong_guess_does_not_burn_the_real_token(client, queued_reset):
    """Otherwise one guess denies the owner their recovery."""
    email = unique_email("reset-guess")
    await _register(client, email)
    await client.post("/api/auth/password/forgot", json={"identifier": email})
    _, token = queued_reset[0]

    bad = await client.post(
        "/api/auth/password/reset",
        json={"token": "not-the-token", "new_password": "whatever-pw-12"},
    )
    assert bad.status_code == 400

    good = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "real-pw-12345"}
    )
    assert good.status_code == 200


async def test_expired_token_is_refused(client, queued_reset, session_maker):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.user import User

    email = unique_email("reset-exp")
    await _register(client, email)
    await client.post("/api/auth/password/forgot", json={"identifier": email})
    _, token = queued_reset[0]

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        user.password_reset_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

    resp = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "too-late-pw-1"}
    )
    assert resp.status_code == 400


async def test_short_password_is_refused(client, queued_reset):
    email = unique_email("reset-short")
    await _register(client, email)
    await client.post("/api/auth/password/forgot", json={"identifier": email})
    _, token = queued_reset[0]

    resp = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "short"}
    )
    assert resp.status_code == 422


async def test_methods_lists_what_a_password_account_has(client):
    email = unique_email("methods-pw")
    await _register(client, email)
    resp = await client.post("/api/auth/methods", json={"identifier": email})
    assert resp.status_code == 200
    body = resp.json()
    assert "password" in body["methods"]
    assert "recovery_code" not in body["methods"], "none were ever created"


async def test_methods_answers_plainly_for_an_unknown_identifier(client):
    """Empty would say «no such account» as loudly as the words would."""
    resp = await client.post(
        "/api/auth/methods", json={"identifier": "nobody-here@vimana.test"}
    )
    assert resp.status_code == 200
    assert resp.json()["methods"] == ["password"]


async def test_methods_offers_reset_only_with_a_verified_address(client, session_maker):
    email = f"methods-unver-{uuidlib.uuid4().hex[:8]}@notverified.test"
    await _register(client, email)
    resp = await client.post("/api/auth/methods", json={"identifier": email})
    assert resp.json()["can_reset"] is False


def test_reset_token_is_stored_hashed():
    """A live token readable from a backup is a takeover kit."""
    from app.core.password_reset import issue_token

    class _U:
        password_reset_hash = None
        password_reset_expires_at = None

    user = _U()
    token = issue_token(user)
    assert token not in (user.password_reset_hash or "")
    assert len(token) > 20


# ── T_SEC.5 pt.2 · the owner is told ─────────────────────────────────────────


@pytest.fixture
def queued_changed(monkeypatch):
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(
        notif.send_password_changed, "delay", lambda uid: sent.append(uid)
    )
    return sent


async def test_reset_announces_the_change(client, queued_reset, queued_changed):
    """Both doors are one event to the mailbox: the account now opens with
    something else."""
    email = unique_email("reset-notice")
    await _register(client, email)
    await client.post("/api/auth/password/forgot", json={"identifier": email})
    _, token = queued_reset[0]

    await client.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": "notice-pw-12345"},
    )
    assert len(queued_changed) == 1


async def test_change_password_announces_the_change(client, queued_changed):
    email = unique_email("change-notice")
    await _register(client, email)
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    grant = await client.post(
        "/api/auth/step-up/verify",
        headers=hdr,
        json={"scope": "change_password", "password": SEED_PASSWORD},
    )
    assert grant.status_code == 200

    resp = await client.put(
        "/api/auth/me/password",
        headers={**hdr, "X-Step-Up-Token": grant.json()["step_up_token"]},
        json={"new_password": "changed-pw-12345"},
    )
    assert resp.status_code == 200
    assert len(queued_changed) == 1


async def test_password_changed_letter_reaches_an_unverified_address(
    sync_test_session, monkeypatch
):
    """Unlike the reset link. That one grants access and needs a proven
    mailbox; this only reports, and withholding it would tell the least
    protected accounts the least."""
    from app.models.user import User
    from app.tasks.notifications import send_password_changed

    sent = []
    from app.tasks import notifications as notif

    monkeypatch.setattr(
        notif, "send_email", lambda to, s, b, html=None: sent.append(to) or True
    )

    email = f"unver-notice-{uuidlib.uuid4().hex[:8]}@notverified.test"
    with sync_test_session() as db:
        user = User(email=email, display_name="U", locale="en")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = str(user.id)

    send_password_changed(user_id)
    assert sent == [email]
