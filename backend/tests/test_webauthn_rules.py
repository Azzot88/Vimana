"""T3.14 pt.1 — the two rules that carry real risk if wrong.

Ceremony verification belongs to `py_webauthn`; there is nothing useful in
re-testing a library. What is ours is the sign-count exception and the
lock-out guard, and both fail in ways that are quiet and expensive.
"""
import uuid

import pytest

from app.core.webauthn import (
    describe_device,
    remaining_ways_in,
    sign_count_is_acceptable,
    would_lock_the_user_out,
)
from app.models.user import User


class _U:
    """Minimal stand-in — the guard only reads three fields."""

    def __init__(self, *, password=False, own_key=False, key_lost=False):
        self.password_hash = "x" if password else None
        self.key_self_custody = own_key
        self.key_lost_at = object() if key_lost else None


# ── sign count ───────────────────────────────────────────────────────────────


def test_zero_stored_accepts_anything():
    """Synced passkeys (iCloud, Google) report 0 forever — they are copied
    between devices by design, so a counter would mean nothing and they keep
    none. A strict `presented > stored` would reject the most common passkey in
    existence on its second use."""
    assert sign_count_is_acceptable(stored=0, presented=0) is True
    assert sign_count_is_acceptable(stored=0, presented=1) is True


def test_counter_must_advance_once_it_is_real():
    """An authenticator that has proven it keeps a counter is held to it: a
    counter going backwards suggests two devices sharing one credential."""
    assert sign_count_is_acceptable(stored=5, presented=6) is True
    assert sign_count_is_acceptable(stored=5, presented=5) is False
    assert sign_count_is_acceptable(stored=5, presented=4) is False
    assert sign_count_is_acceptable(stored=5, presented=0) is False


# ── lock-out guard ───────────────────────────────────────────────────────────


def test_passwordless_single_passkey_cannot_be_removed():
    """One passkey, no password, no own key — deleting it is not a logout, it
    is losing the account, and email is optional so there may be no way back."""
    user = _U()
    assert would_lock_the_user_out(user, credential_count=1) is True


def test_second_passkey_makes_the_first_removable():
    assert would_lock_the_user_out(_U(), credential_count=2) is False


def test_password_counts_as_a_way_in():
    assert would_lock_the_user_out(_U(password=True), credential_count=1) is False


def test_own_nostr_key_counts_as_a_way_in():
    assert would_lock_the_user_out(_U(own_key=True), credential_count=1) is False


def test_lost_key_does_not_count():
    """`declare-lost` (T3.12) retires the identity — it can no longer sign, so
    it is not a door. Counting it would let the last real one be deleted."""
    user = _U(own_key=True, key_lost=True)
    assert remaining_ways_in(user, credential_count=1) == 1
    assert would_lock_the_user_out(user, credential_count=1) is True


def test_no_ways_left_is_also_locked_out():
    """Zero is not better than one — guards against an off-by-one that only
    refuses at exactly 1."""
    assert would_lock_the_user_out(_U(), credential_count=0) is True


def test_email_is_not_a_way_in():
    """Confirming an address is not signing in. Counting it would let someone
    delete their last passkey and discover email cannot get them back."""
    user = _U()
    user.email = "someone@vimana.test"
    user.email_verified_at = object()
    assert would_lock_the_user_out(user, credential_count=1) is True


# ── device labels ────────────────────────────────────────────────────────────


def test_hardware_key_is_recognised():
    """YubiKey: not backed up, plugged in or tapped. Needs no special code
    path — the same WebAuthn flow — but the UI should say which it is, because
    losing a hardware key and losing a synced credential differ."""
    assert (
        describe_device(transports=["usb", "nfc"], backed_up=False) == "hardware_key"
    )


def test_synced_and_device_bound_are_distinguished():
    assert describe_device(transports=["internal"], backed_up=True) == "synced_passkey"
    assert (
        describe_device(transports=["internal"], backed_up=False) == "device_passkey"
    )
    assert describe_device(transports=None, backed_up=False) == "device_passkey"


# ── model wiring ─────────────────────────────────────────────────────────────


async def test_credential_row_round_trips(session_maker, seed_carrier):
    from app.models.webauthn import WebAuthnCredential

    cred_id = uuid.uuid4().bytes
    async with session_maker() as db:
        db.add(
            WebAuthnCredential(
                user_id=seed_carrier.id,
                credential_id=cred_id,
                public_key=b"pk",
                transports=["internal", "hybrid"],
                device_name="Test device",
            )
        )
        await db.commit()

    from sqlalchemy import select

    async with session_maker() as db:
        row = (
            await db.execute(
                select(WebAuthnCredential).where(
                    WebAuthnCredential.credential_id == cred_id
                )
            )
        ).scalar_one()
        assert row.sign_count == 0
        assert row.backed_up is False
        assert row.transports == ["internal", "hybrid"]


async def test_credential_id_is_globally_unique(session_maker, seed_carrier, seed_sender):
    """Login is usernameless, so the credential id is all the server gets — it
    has to identify one account on its own."""
    from sqlalchemy.exc import IntegrityError

    from app.models.webauthn import WebAuthnCredential

    shared = uuid.uuid4().bytes
    async with session_maker() as db:
        db.add(
            WebAuthnCredential(
                user_id=seed_carrier.id, credential_id=shared, public_key=b"a"
            )
        )
        await db.commit()

    async with session_maker() as db:
        db.add(
            WebAuthnCredential(
                user_id=seed_sender.id, credential_id=shared, public_key=b"b"
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
