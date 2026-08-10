"""T3.28 — one door for signing in and signing up."""
import uuid as uuidlib

import pytest

from tests.conftest import SEED_PASSWORD, unique_email


@pytest.fixture
def queued_codes(monkeypatch):
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: sent.append(a))
    return sent


async def _request(client, identifier: str):
    return await client.post(
        "/api/auth/otp/request",
        json={"identifier": identifier, "channel": "email", "locale": "en"},
    )


async def test_request_answers_202_for_an_unknown_address(client, queued_codes):
    """The screen must not become a directory of who banks here."""
    resp = await _request(client, unique_email("otp-unknown"))
    assert resp.status_code == 202


async def test_request_answers_202_for_a_known_address(client, queued_codes):
    email = unique_email("otp-known")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "known"},
    )
    resp = await _request(client, email)
    assert resp.status_code == 202, "identical to the unknown case"


async def test_request_answers_202_for_nonsense(client, queued_codes):
    resp = await _request(client, "not-an-identifier")
    assert resp.status_code == 202
    assert queued_codes == []


async def test_a_code_creates_an_account_that_did_not_exist(
    client, queued_codes, session_maker
):
    from sqlalchemy import select

    from app.models.user import User

    email = unique_email("otp-new")
    await _request(client, email)
    code = queued_codes[-1][2]

    resp = await client.post(
        "/api/auth/otp/verify", json={"identifier": email, "code": code}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert user.password_hash is None, "no password was ever chosen"
        assert user.nostr_pubkey, "the service keypair is issued like everywhere else"
        assert user.email_verified_at is not None, "the code *was* the proof"


async def test_a_code_signs_in_an_account_that_exists(client, queued_codes):
    email = unique_email("otp-existing")
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "existing"},
    )
    user_id = reg.json()["id"]

    await _request(client, email)
    code = queued_codes[-1][2]
    resp = await client.post(
        "/api/auth/otp/verify", json={"identifier": email, "code": code}
    )
    assert resp.status_code == 200

    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    )
    assert me.json()["id"] == user_id, "the same account, not a second one"


async def test_the_password_still_works_afterwards(client, queued_codes):
    """Signing in by code must not quietly retire the other way in."""
    email = unique_email("otp-both")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "both"},
    )
    await _request(client, email)
    await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": queued_codes[-1][2]},
    )
    resp = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    assert resp.status_code == 200


async def test_a_code_works_once(client, queued_codes):
    email = unique_email("otp-once")
    await _request(client, email)
    code = queued_codes[-1][2]
    first = await client.post(
        "/api/auth/otp/verify", json={"identifier": email, "code": code}
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/auth/otp/verify", json={"identifier": email, "code": code}
    )
    assert second.status_code == 400


async def test_a_wrong_code_is_refused(client, queued_codes):
    email = unique_email("otp-wrong")
    await _request(client, email)
    resp = await client.post(
        "/api/auth/otp/verify", json={"identifier": email, "code": "000000"}
    )
    assert resp.status_code == 400


async def test_a_contact_code_cannot_be_spent_to_become_the_account(
    client, queued_codes, monkeypatch
):
    """The purposes are not interchangeable, and this is why they are separate.

    A code minted to add a second address to an account must never be enough to
    *become* that address's owner.
    """
    email = unique_email("otp-purpose")
    await client.post(
        "/api/auth/contact/request-code",
        json={"identifier": email, "channel": "email"},
    )
    contact_code = queued_codes[-1][2]

    resp = await client.post(
        "/api/auth/otp/verify", json={"identifier": email, "code": contact_code}
    )
    assert resp.status_code == 400


async def test_asking_twice_in_a_row_is_told_to_wait(client, queued_codes):
    email = unique_email("otp-cool")
    assert (await _request(client, email)).status_code == 202
    assert (await _request(client, email)).status_code == 429


async def test_the_new_account_gets_a_provisional_name(
    client, queued_codes, session_maker
):
    """Refusing to finish without a name would burn the code the visitor just
    spent — the worst possible answer to a correct one."""
    from sqlalchemy import select

    from app.models.user import User

    email = unique_email("otp-name")
    await _request(client, email)
    await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": queued_codes[-1][2]},
    )

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert user.display_name == email.split("@")[0]


async def test_the_login_contact_is_marked_as_such(client, queued_codes, session_maker):
    from sqlalchemy import select

    from app.models.contact import UserContact

    email = unique_email("otp-flag")
    await _request(client, email)
    await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": queued_codes[-1][2]},
    )

    async with session_maker() as db:
        row = (
            await db.execute(
                select(UserContact).where(
                    UserContact.channel == "email", UserContact.value == email
                )
            )
        ).scalar_one()
        assert row.is_login is True and row.verified_at is not None


# ── T3.28 pt.4 · one button: the password travels with the code ──────────────


async def test_a_password_typed_at_the_door_lands_on_the_new_account(
    client, queued_codes, session_maker
):
    """Nothing is stored before the code proves the address.

    Creating the account on submit would let a stranger squat on somebody
    else's address, and a typo would produce a second account instead of an
    error. So the browser holds the password and it lands here.
    """
    from sqlalchemy import select

    from app.models.user import User

    email = unique_email("otp-pw")
    await _request(client, email)
    resp = await client.post(
        "/api/auth/otp/verify",
        json={
            "identifier": email,
            "code": queued_codes[-1][2],
            "password": "chosen-at-the-door-1",
        },
    )
    assert resp.status_code == 200

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert user.password_hash is not None

    signed_in = await client.post(
        "/api/auth/login", json={"login": email, "password": "chosen-at-the-door-1"}
    )
    assert signed_in.status_code == 200


async def test_a_password_is_ignored_for_an_account_that_exists(
    client, queued_codes
):
    """Otherwise whoever holds the mailbox performs a silent password reset,
    with no screen saying that is what happened."""
    email = unique_email("otp-pw-existing")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "existing"},
    )

    await _request(client, email)
    await client.post(
        "/api/auth/otp/verify",
        json={
            "identifier": email,
            "code": queued_codes[-1][2],
            "password": "not-my-password-1",
        },
    )

    assert (
        await client.post(
            "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
        )
    ).status_code == 200, "the original password still works"
    assert (
        await client.post(
            "/api/auth/login", json={"login": email, "password": "not-my-password-1"}
        )
    ).status_code == 401, "and the typed one never took effect"


async def test_no_password_still_creates_a_passwordless_account(
    client, queued_codes, session_maker
):
    from sqlalchemy import select

    from app.models.user import User

    email = unique_email("otp-nopw")
    await _request(client, email)
    await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": queued_codes[-1][2]},
    )

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert user.password_hash is None


async def test_a_code_claims_an_account_whose_address_was_never_confirmed(
    client, queued_codes, session_maker
):
    """Without this the second account on the same address dies on the UNIQUE —
    a 500 handed to the person who just proved they read that mailbox.

    The address is confirmed on the way through: the code is exactly the proof
    the account was created without.
    """
    from sqlalchemy import select

    from app.models.user import User

    # `@notverified.test` is outside the auto-verify list, so registration
    # leaves the address unproven — the state this branch exists for.
    email = f"claim-{uuidlib.uuid4().hex[:8]}@notverified.test"
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "claimed"},
    )
    user_id = reg.json()["id"]

    await _request(client, email)
    resp = await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": queued_codes[-1][2]},
    )
    assert resp.status_code == 200

    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    )
    assert me.json()["id"] == user_id, "the same account, not a second one"

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert user.email_verified_at is not None, "the code was the missing proof"
