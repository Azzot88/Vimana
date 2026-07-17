"""T2.1 — verification helpers: container encryption + level aggregation.

**Container encryption model (MVP):**
- AES-256-GCM.
- Key = owner's Nostr `nsec` first 32 bytes (nsec IS a valid 32-byte AES-256 key).
- Custodial users: server has `nsec_encrypted` → can encrypt/decrypt.
- Self-custody users: server has no nsec → **upload returns 422** in MVP. Full
  self-custody support arrives with T2.3 (threshold 2-of-3) which lets the
  owner encrypt client-side and share shares with sender/carrier/arbiter.

**Sanctions check (MVP):** stub returns `clean`. Real OFAC/EU wiring later.
"""
from __future__ import annotations

import hashlib
import os
from typing import Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keypair import decrypt_nsec
from app.models.user import User
from app.models.verification import (
    SanctionsStatus,
    VerificationBadge,
    VerificationLevel,
)


class ContainerEncryptionError(RuntimeError):
    pass


def _nsec_to_aes_key(nsec_hex: str) -> bytes:
    key = bytes.fromhex(nsec_hex)
    if len(key) != 32:
        raise ContainerEncryptionError("nsec must be 32 bytes")
    return key


def encrypt_container(owner: User, plaintext: bytes) -> tuple[bytes, bytes]:
    """Encrypt raw document bytes with owner's nsec. Returns (nonce, ciphertext).

    Raises `ContainerEncryptionError` for self-custody users (nsec unavailable).
    """
    if owner.key_self_custody or owner.nsec_encrypted is None:
        raise ContainerEncryptionError(
            "Self-custody accounts can't upload documents in MVP (T2.3 will add "
            "threshold encryption for client-side encrypt)."
        )
    nsec_hex = decrypt_nsec(bytes(owner.nsec_nonce), bytes(owner.nsec_encrypted))
    aes_key = _nsec_to_aes_key(nsec_hex)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    return nonce, ciphertext


def decrypt_container(owner: User, nonce: bytes, ciphertext: bytes) -> bytes:
    """Decrypt for the owner (custodial only)."""
    if owner.key_self_custody or owner.nsec_encrypted is None:
        raise ContainerEncryptionError(
            "Owner is self-custody — server can't decrypt"
        )
    nsec_hex = decrypt_nsec(bytes(owner.nsec_nonce), bytes(owner.nsec_encrypted))
    aes_key = _nsec_to_aes_key(nsec_hex)
    return AESGCM(aes_key).decrypt(nonce, bytes(ciphertext), None)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_sanctions_stub(_name: str | None, _country: str | None) -> SanctionsStatus:
    """MVP stub. Real OFAC SDN + EU fuzzy match wired in a follow-up task."""
    return SanctionsStatus.clean


# ─────────────────────────────────────────────────────────────
# Level aggregation
# ─────────────────────────────────────────────────────────────

_LEVEL_RANK = {"auto": 1, "peer": 2, "kyc": 3}


async def refresh_highest_level(user_id, db: AsyncSession) -> str | None:
    """Recompute `User.highest_verification_level` from active badges.

    Call after INSERT / revoke of `VerificationBadge`. Cheap query (indexed).
    """
    result = await db.execute(
        select(VerificationBadge.level).where(
            VerificationBadge.subject_id == user_id,
            VerificationBadge.revoked_at.is_(None),
        )
    )
    levels: Iterable = result.scalars().all()
    if not levels:
        new_level = None
    else:
        # levels come back as VerificationLevel enum objects
        vals = [l.value if hasattr(l, "value") else str(l) for l in levels]
        new_level = max(vals, key=lambda v: _LEVEL_RANK.get(v, 0))

    user = await db.get(User, user_id)
    if user is not None and user.highest_verification_level != new_level:
        user.highest_verification_level = new_level
        await db.flush()
    return new_level
