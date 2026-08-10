"""T3.25 — contacts as rows, and one code lifecycle for every channel."""
import uuid as uuidlib

import pytest

from tests.conftest import SEED_PASSWORD, unique_email


# ── normalisation ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    ["+971501234567", "+971 50 123 45 67", "+971-50-123-4567", "  +971501234567  "],
)
def test_one_number_written_four_ways_is_one_string(raw):
    """The whole reason the table can carry a UNIQUE at all."""
    from app.core.contacts import normalize

    assert normalize("sms", raw) == "+971501234567"


def test_a_number_without_a_country_is_refused_not_guessed():
    """An international product cannot guess a region, and guessing wrong turns
    a Dubai number into a US one silently."""
    from app.core.contacts import normalize

    assert normalize("sms", "0501234567") is None


def test_nonsense_does_not_become_a_contact():
    from app.core.contacts import normalize

    assert normalize("sms", "+1") is None
    assert normalize("sms", "not a phone") is None
    assert normalize("email", "not-an-email") is None
    assert normalize("telegram", "not-an-id") is None


def test_email_is_lowercased_and_trimmed():
    from app.core.contacts import normalize

    assert normalize("email", "  Someone@Example.TEST ") == "someone@example.test"


def test_telegram_accepts_group_ids():
    from app.core.contacts import normalize

    assert normalize("telegram", "-100123456") == "-100123456"


# ── the rows ─────────────────────────────────────────────────────────────────


async def _register(client, email: str):
    return await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": email[:8]},
    )


async def _contacts(session_maker, user_id):
    from sqlalchemy import select

    from app.models.contact import UserContact

    async with session_maker() as db:
        rows = (
            await db.execute(
                select(UserContact).where(UserContact.user_id == user_id)
            )
        ).scalars().all()
        return {(r.channel, r.value): r.verified_at for r in rows}


async def test_registration_records_the_email_contact(client, session_maker):
    email = unique_email("contact-reg")
    resp = await _register(client, email)
    user_id = uuidlib.UUID(resp.json()["id"])

    rows = await _contacts(session_maker, user_id)
    assert ("email", email) in rows


async def test_an_unconfirmed_claim_does_not_reserve_the_value(client, session_maker):
    """Two accounts may both *claim* a number; only a confirmed one owns it.

    Without the partial index, typing somebody else's number first would lock
    its real owner out of the platform permanently.
    """
    from app.models.contact import UserContact

    number = "+971509998877"
    ids = []
    for i in range(2):
        resp = await _register(client, unique_email(f"claim{i}"))
        ids.append(uuidlib.UUID(resp.json()["id"]))

    async with session_maker() as db:
        for user_id in ids:
            db.add(UserContact(user_id=user_id, channel="sms", value=number))
        await db.commit()  # must not raise

    for user_id in ids:
        assert ("sms", number) in await _contacts(session_maker, user_id)


async def test_a_confirmed_value_belongs_to_one_account(client, session_maker):
    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    from app.models.contact import UserContact

    number = "+971507776655"
    ids = []
    for i in range(2):
        resp = await _register(client, unique_email(f"own{i}"))
        ids.append(uuidlib.UUID(resp.json()["id"]))

    async with session_maker() as db:
        db.add(
            UserContact(
                user_id=ids[0],
                channel="sms",
                value=number,
                verified_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    with pytest.raises(IntegrityError):
        async with session_maker() as db:
            db.add(
                UserContact(
                    user_id=ids[1],
                    channel="sms",
                    value=number,
                    verified_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()


async def test_phone_in_the_profile_is_normalised_and_recorded(
    client, session_maker
):
    email = unique_email("phone-edit")
    resp = await _register(client, email)
    user_id = uuidlib.UUID(resp.json()["id"])
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    saved = await client.patch(
        "/api/auth/me", headers=hdr, json={"phone": "+971 50 111 22 33"}
    )
    assert saved.status_code == 200
    assert saved.json()["phone"] == "+971501112233"

    rows = await _contacts(session_maker, user_id)
    assert rows[("sms", "+971501112233")] is None, "typed, not proven"


async def test_an_unparseable_phone_is_refused(client):
    email = unique_email("phone-bad")
    await _register(client, email)
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.patch("/api/auth/me", headers=hdr, json={"phone": "0501234567"})
    assert resp.status_code == 422


# ── the code lifecycle ───────────────────────────────────────────────────────


async def test_a_code_can_be_issued_and_used(session_maker):
    from app.core.contact_verification import issue, verify

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    async with session_maker() as db:
        code = await issue(db, "sms", value)
        await db.commit()
    async with session_maker() as db:
        challenge = await verify(db, "sms", value, code)
        await db.commit()
    assert challenge.value == value


async def test_a_used_code_does_not_work_twice(session_maker):
    from app.core.contact_verification import NoCodeIssued, issue, verify

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    async with session_maker() as db:
        code = await issue(db, "sms", value)
        await db.commit()
    async with session_maker() as db:
        await verify(db, "sms", value, code)
        await db.commit()
    with pytest.raises(NoCodeIssued):
        async with session_maker() as db:
            await verify(db, "sms", value, code)


async def test_running_out_of_attempts_burns_the_code(session_maker):
    """Not merely rejects it: a code surviving its own limit invites waiting
    for the counter to be forgotten."""
    from app.core.contact_verification import (
        MAX_ATTEMPTS,
        CodeInvalid,
        NoCodeIssued,
        TooManyAttempts,
        issue,
        verify,
    )

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    async with session_maker() as db:
        code = await issue(db, "sms", value)
        await db.commit()

    for _ in range(MAX_ATTEMPTS - 1):
        with pytest.raises(CodeInvalid):
            async with session_maker() as db:
                await verify(db, "sms", value, "000000")
                await db.commit()
    with pytest.raises(TooManyAttempts):
        async with session_maker() as db:
            await verify(db, "sms", value, "000000")
            await db.commit()

    with pytest.raises(NoCodeIssued):
        async with session_maker() as db:
            await verify(db, "sms", value, code)


async def test_an_expired_code_is_refused(session_maker):
    from datetime import datetime, timedelta, timezone

    from app.core.contact_verification import CodeExpired, issue, verify

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    async with session_maker() as db:
        code = await issue(db, "sms", value, now=past)
        await db.commit()
    with pytest.raises(CodeExpired):
        async with session_maker() as db:
            await verify(db, "sms", value, code)
            await db.commit()


async def test_asking_again_immediately_is_refused(session_maker):
    """Per value, not per account: at sign-up there is no account yet."""
    from app.core.contact_verification import CooldownActive, issue

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    async with session_maker() as db:
        await issue(db, "sms", value)
        await db.commit()
    with pytest.raises(CooldownActive):
        async with session_maker() as db:
            await issue(db, "sms", value)


async def test_a_new_code_replaces_the_old_one(session_maker):
    """Two live codes for one address means the older is a second key nobody
    remembers issuing."""
    from datetime import datetime, timedelta, timezone

    from app.core.contact_verification import CodeInvalid, issue, verify

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    async with session_maker() as db:
        first = await issue(db, "sms", value)
        await db.commit()
    later = datetime.now(timezone.utc) + timedelta(minutes=2)
    async with session_maker() as db:
        second = await issue(db, "sms", value, now=later)
        await db.commit()

    assert first != second
    with pytest.raises(CodeInvalid):
        async with session_maker() as db:
            await verify(db, "sms", value, first)
            await db.commit()


async def test_the_code_is_stored_hashed(session_maker):
    from sqlalchemy import select

    from app.core.contact_verification import issue
    from app.models.contact import VerificationChallenge

    value = f"+9715{uuidlib.uuid4().int % 10**8:08d}"
    async with session_maker() as db:
        code = await issue(db, "sms", value)
        await db.commit()
    async with session_maker() as db:
        row = (
            await db.execute(
                select(VerificationChallenge).where(
                    VerificationChallenge.value == value
                )
            )
        ).scalar_one()
        assert code not in row.code_hash


def test_generated_codes_are_six_digits():
    from app.core.contact_verification import generate_code

    for _ in range(50):
        code = generate_code()
        assert len(code) == 6 and code.isdigit()
