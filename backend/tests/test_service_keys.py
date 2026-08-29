"""T3.12 pt.1 — service key backfill + identity schema invariants.

A *service key* is not an identity (`D-KEY-IS-IDENTITY`): the platform issues
it, holds the nsec, and uses it to encrypt and sign on the user's behalf. These
tests pin the two properties the rest of Phase 3.7 leans on — every account has
one, and no two accounts share an npub.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.service_keys import ensure_service_keys
from app.models.user import User


async def _make_keyless(session_maker, *, role: str = "user") -> str:
    async with session_maker() as db:
        user = User(
            email=f"keyless-{uuid.uuid4().hex[:8]}@vimana.test",
            password_hash=None,
            display_name="Keyless",
            roles=[] if role == "user" else [role],
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.id)


async def _get(session_maker, user_id: str) -> User:
    async with session_maker() as db:
        return await db.get(User, user_id)


async def test_backfill_issues_key_to_keyless_account(session_maker):
    user_id = await _make_keyless(session_maker)

    async with session_maker() as db:
        issued = await ensure_service_keys(db)
    assert issued >= 1

    user = await _get(session_maker, user_id)
    assert user.nostr_pubkey and len(user.nostr_pubkey) == 64
    assert user.nsec_encrypted is not None
    assert user.nsec_nonce is not None
    # A service key is custodial by definition — identity starts elsewhere.
    assert user.key_self_custody is False
    assert user.identity_established is False


async def test_backfill_covers_arbiter(session_maker):
    """The live defect this fixes: `api/threshold.py` needs the arbiter's npub,
    and the arbiter account had none — threshold 2-of-3 could not assemble."""
    user_id = await _make_keyless(session_maker, role="arbiter")

    async with session_maker() as db:
        await ensure_service_keys(db)

    user = await _get(session_maker, user_id)
    assert user.nostr_pubkey is not None


async def test_backfill_is_idempotent(session_maker):
    user_id = await _make_keyless(session_maker)

    async with session_maker() as db:
        await ensure_service_keys(db)
    first = (await _get(session_maker, user_id)).nostr_pubkey

    async with session_maker() as db:
        issued_again = await ensure_service_keys(db)

    assert issued_again == 0
    assert (await _get(session_maker, user_id)).nostr_pubkey == first


async def test_backfill_leaves_existing_keys_alone(session_maker, seed_carrier):
    """Replacing a key that already signed records would orphan those
    signatures — the backfill must never touch an account that has one."""
    before = seed_carrier.nostr_pubkey
    assert before is not None

    async with session_maker() as db:
        await ensure_service_keys(db)

    assert (await _get(session_maker, str(seed_carrier.id))).nostr_pubkey == before


async def test_npub_is_unique(session_maker, seed_carrier):
    """Two accounts sharing an npub would make key-based login ambiguous."""
    async with session_maker() as db:
        clash = User(
            email=f"clash-{uuid.uuid4().hex[:8]}@vimana.test",
            password_hash=None,
            display_name="Clash",
            nostr_pubkey=seed_carrier.nostr_pubkey,
        )
        db.add(clash)
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_key_lost_is_exposed_on_user_payloads(client, carrier_headers):
    """`key_lost` sits on `UserOut`, so every serialisation of a user carries
    it — a dead identity cannot be hidden by picking a different endpoint."""
    resp = await client.get("/api/auth/me", headers=carrier_headers)
    assert resp.status_code == 200
    assert resp.json()["key_lost"] is False


async def test_key_lost_property_tracks_column(session_maker):
    from datetime import datetime, timezone

    user_id = await _make_keyless(session_maker)
    async with session_maker() as db:
        user = await db.get(User, user_id)
        assert user.key_lost is False
        user.key_lost_at = datetime.now(timezone.utc)
        await db.commit()

    assert (await _get(session_maker, user_id)).key_lost is True


async def test_service_keys_are_distinct(session_maker):
    """Two backfilled accounts must not end up with the same key."""
    a = await _make_keyless(session_maker)
    b = await _make_keyless(session_maker)

    async with session_maker() as db:
        await ensure_service_keys(db)

    ua = await _get(session_maker, a)
    ub = await _get(session_maker, b)
    assert ua.nostr_pubkey != ub.nostr_pubkey


async def test_no_account_left_without_a_key(session_maker):
    await _make_keyless(session_maker)

    async with session_maker() as db:
        await ensure_service_keys(db)
        remaining = (
            await db.execute(select(User).where(User.nostr_pubkey.is_(None)))
        ).scalars().all()

    assert remaining == []
