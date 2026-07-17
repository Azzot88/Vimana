"""T2.3 — Threshold 2-of-3 endpoints."""
from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.keypair import decrypt_nsec
from app.core.permissions import Permission, require_perm
from app.core.threshold import get_arbiter_user_id, nip04_decrypt
from app.models.deal import Deal, DealEvent, DealEventType, DealVaultMessage, Dispute
from app.models.user import User

router = APIRouter()


@router.get("/arbiter-info")
async def get_arbiter_info(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover the platform arbiter's user id + npub so clients can encrypt
    a share under it when writing e2e vault messages.

    Returns 503 until ops sets `ARBITER_USER_ID` env and the user exists.
    """
    arbiter_id = get_arbiter_user_id()
    if arbiter_id is None:
        raise HTTPException(
            status_code=503,
            detail="Platform arbiter not configured (ARBITER_USER_ID unset)",
        )
    arbiter = await db.get(User, arbiter_id)
    if arbiter is None or arbiter.nostr_pubkey is None:
        raise HTTPException(
            status_code=503, detail="Platform arbiter user missing or has no npub"
        )
    return {"user_id": str(arbiter.id), "npub": arbiter.nostr_pubkey}


@router.post("/dealvault/messages/{message_id}/reveal-my-share")
async def reveal_my_share(
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the caller's own wrapped share for a message.

    Client uses this to fetch the ECIES envelope, then unwraps locally with
    their own nsec (self-custody) or via server-signing (custodial fallback in
    a follow-up). Server sends only the envelope; the underlying share never
    leaks in plaintext through this endpoint.
    """
    msg = await db.get(DealVaultMessage, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if not msg.is_e2e or not msg.wrapped_shares:
        raise HTTPException(status_code=400, detail="Message is not e2e-encrypted")

    deal = await db.get(Deal, msg.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    role: str | None = None
    if current_user.id == deal.sender_id:
        role = "sender"
    elif current_user.id == deal.carrier_id:
        role = "carrier"
    else:
        raise HTTPException(status_code=403, detail="Not a deal participant")

    envelope = msg.wrapped_shares.get(role)
    if envelope is None:
        raise HTTPException(status_code=404, detail=f"No wrapped share for {role}")
    return {"role": role, "envelope": envelope}


@router.post("/disputes/{deal_id}/arbiter-reveal")
async def arbiter_reveal(
    deal_id: uuid.UUID,
    arbiter: User = Depends(require_perm(Permission.THRESHOLD_ARBITER_REVEAL)),
    db: AsyncSession = Depends(get_db),
):
    """Arbiter unwraps their own share for every e2e message in the deal.

    Preconditions: dispute exists and is `open` or `claimed`. Server uses the
    arbiter's custodial nsec (T2.2 pt.1) to ECIES-decrypt the arbiter share of
    each message. Response is a per-message plaintext share (base64) — arbiter's
    client will need one more share (from a cooperating party via
    `/reveal-my-share`) to reconstruct the session key.

    Writes an append-only `arbiter_share_revealed` DealEvent as audit trail.
    """
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    dispute_row = await db.execute(select(Dispute).where(Dispute.deal_id == deal_id))
    dispute = dispute_row.scalar_one_or_none()
    if dispute is None:
        raise HTTPException(status_code=400, detail="No dispute for this deal")

    if arbiter.nsec_encrypted is None or arbiter.nsec_nonce is None:
        raise HTTPException(
            status_code=422,
            detail="Arbiter has no custodial nsec — self-custody arbiter reveal not supported yet",
        )
    arbiter_nsec_hex = decrypt_nsec(
        bytes(arbiter.nsec_nonce), bytes(arbiter.nsec_encrypted)
    )

    msg_rows = await db.execute(
        select(DealVaultMessage).where(
            DealVaultMessage.deal_id == deal_id,
            DealVaultMessage.is_e2e.is_(True),
        )
    )
    messages = list(msg_rows.scalars())

    revealed: list[dict] = []
    for msg in messages:
        shares = msg.wrapped_shares or {}
        envelope = shares.get("arbiter")
        if envelope is None:
            continue
        if not msg.nostr_pubkey:
            # Author didn't have a keypair at write time — can't verify sender.
            continue
        share_bytes = nip04_decrypt(envelope, arbiter_nsec_hex, msg.nostr_pubkey)
        revealed.append(
            {
                "message_id": str(msg.id),
                "arbiter_share_b64": base64.b64encode(share_bytes).decode("ascii"),
            }
        )

    audit = DealEvent(
        deal_id=deal_id,
        event_type=DealEventType.arbiter_opened,
        actor_id=arbiter.id,
        payload={"kind": "arbiter_share_revealed", "count": len(revealed)},
    )
    db.add(audit)
    await db.commit()

    return {"revealed": revealed, "audit_event_id": str(audit.id)}
