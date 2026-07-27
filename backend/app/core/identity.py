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
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealVaultMessage
from app.models.user import User


async def establish_blockers(db: AsyncSession, user: User) -> list[str]:
    """Reasons the transition would destroy data, empty list if it is safe.

    Identity containers are no longer listed: pt.2b re-wraps them in place
    (`core.verification.rewrap_container_to_identity`). What remains is the case
    the server genuinely cannot fix on its own — see below.
    """
    blockers: list[str] = []

    # A read package is decrypted as ECDH(reader_priv, message_author_pub), so
    # producing one readable by the new key needs ECDH(author_priv, new_pub) —
    # the *author's* private key, which the platform does not have unless the
    # author happens to be this same custodial user. Re-wrapping therefore
    # cannot be done server-side without changing the stored format to carry a
    # per-package sender pubkey, which touches dealvault, threshold and
    # arbiter-reveal together. Until then, refuse rather than strand the vault.
    e2e_messages = await db.scalar(
        select(func.count())
        .select_from(DealVaultMessage)
        .join(Deal, Deal.id == DealVaultMessage.deal_id)
        .where(
            DealVaultMessage.is_e2e.is_(True),
            or_(Deal.sender_id == user.id, Deal.carrier_id == user.id),
        )
    )
    if e2e_messages:
        blockers.append(
            f"{e2e_messages} end-to-end vault message(s) are addressed to the "
            "service key and cannot be re-wrapped yet"
        )

    return blockers


def require_live_identity(user: User) -> None:
    """Refuse actions that would need a signature the user can no longer make."""
    if user.key_lost_at is not None:
        raise HTTPException(
            status_code=403,
            detail="Identity key was declared lost — this account can no longer act",
        )
