"""T3.12 pt.2 — identity state: what blocks the transition, what a dead key costs.

Two guards live here.

`establish_blockers` answers "would taking your own key make something of yours
unreadable?". At the moment of transition the platform destroys the service
nsec it holds. Anything encrypted *to that key* — identity containers, vault
read-packages — becomes unreadable by everyone, including the owner, because
the new key has no relationship to the old one. Rather than let that happen
silently, the transition refuses and says what stands in the way. Lifting these
blockers means re-wrapping that content to the new key, which is pt.2b.

`require_live_identity` answers "can this account still act?". An account that
declared its key lost keeps its login (a passkey still works) but can no longer
sign anything or read its own encrypted history. Letting it start new deals
would put a counterparty opposite someone who cannot sign a single record.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealVaultMessage
from app.models.user import User


async def establish_blockers(db: AsyncSession, user: User) -> list[str]:
    """Reasons the transition would destroy data, empty list if it is safe.

    Currently always empty: identity containers move in pt.2b
    (`core.verification.rewrap_container_to_identity`) and vault envelopes in
    pt.2c (`rewrap_vault_envelopes` below). Kept as the single place to refuse
    from — anything encrypted to the service key that a future feature adds
    must either be re-wrapped here or listed here, and silently doing neither
    is the failure mode this function exists to prevent.
    """
    return []


async def rewrap_vault_envelopes(
    db: AsyncSession,
    user: User,
    *,
    old_nsec_hex: str,
    old_npub_hex: str,
    new_npub_hex: str,
) -> int:
    """Re-address this user's e2e envelopes to their new key. Returns the count.

    A read package is decrypted as ECDH(reader_priv, sender_pub). Re-addressing
    one to a different reader needs the *sender's* private key — which the
    platform does not have, since the sender is whoever wrote the message. The
    way through is not to keep the original sender: the platform re-encrypts
    with the retiring service key as sender and records that in the envelope
    (pt.2c format). ECDH being symmetric, the user's new private key plus the
    recorded service pubkey recovers the same session key.

    Only entries addressed to *this* user are touched. Everyone else's packages
    on the same message keep their sender and stay readable.

    Raises `ValueError` if any re-wrap cannot be proven to round-trip, so the
    caller's transaction rolls back with the service key still intact.
    """
    from app.core.threshold import envelope_parts, make_envelope, nip04_decrypt
    from app.core.threshold import nip04_encrypt

    rows = await db.execute(
        select(DealVaultMessage, Deal)
        .join(Deal, Deal.id == DealVaultMessage.deal_id)
        .where(
            DealVaultMessage.is_e2e.is_(True),
            or_(
                Deal.sender_id == user.id,
                Deal.carrier_id == user.id,
                Deal.recipient_id == user.id,
            ),
        )
    )

    rewrapped = 0
    for msg, deal in rows.all():
        if deal.sender_id == user.id:
            key = "sender"
        elif deal.carrier_id == user.id:
            key = "carrier"
        else:
            key = f"recipient_{user.id}"

        for field in ("read_packages", "wrapped_shares"):
            stored = getattr(msg, field) or {}
            entry = stored.get(key)
            if entry is None:
                continue

            ciphertext, sender_pubkey = envelope_parts(entry, msg.nostr_pubkey)
            if not sender_pubkey:
                raise ValueError(
                    f"message {msg.id}: {field}[{key}] has no sender pubkey"
                )
            plaintext = nip04_decrypt(ciphertext, old_nsec_hex, sender_pubkey)
            new_ct = nip04_encrypt(plaintext, old_nsec_hex, new_npub_hex)

            # Prove it round-trips before the sender key is destroyed. Symmetric
            # ECDH lets the platform read what only the new owner will be able
            # to read afterwards.
            if nip04_decrypt(new_ct, old_nsec_hex, new_npub_hex) != plaintext:
                raise ValueError(f"message {msg.id}: {field}[{key}] failed round-trip")

            # JSON columns only register a change on reassignment.
            updated = dict(stored)
            updated[key] = make_envelope(new_ct, old_npub_hex)
            setattr(msg, field, updated)
            rewrapped += 1

    return rewrapped


def require_live_identity(user: User) -> None:
    """Refuse actions that would need a signature the user can no longer make."""
    if user.key_lost_at is not None:
        raise HTTPException(
            status_code=403,
            detail="Identity key was declared lost — this account can no longer act",
        )
