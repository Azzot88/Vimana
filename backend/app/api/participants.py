"""T3.3 — Deal recipient invite / join / revoke / list."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.deal import Deal, DealParticipant, DealParticipantRole
from app.models.user import User

router = APIRouter()


class InviteOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    role: str
    invite_token: str
    invite_url: str  # convenience — the shareable URL
    invited_at: datetime


class ParticipantOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    user_id: uuid.UUID | None
    display_name: str | None
    npub: str | None
    role: str
    invited_at: datetime
    accepted_at: datetime | None


def _invite_url(token: str) -> str:
    import os

    base = os.getenv("VIMANA_PUBLIC_URL", "https://vimana.dealvault.club")
    return f"{base}/join/deal/{token}"


@router.post("/deals/{deal_id}/invite-recipient", response_model=InviteOut, status_code=201)
async def invite_recipient(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sender-only: create a shareable invite token for a recipient.

    Recipient accepts the link, logs in / registers, and gets attached via
    `POST /deals/join/{token}`. Multiple recipients per deal are allowed — each
    call issues a fresh token.
    """
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only sender can invite recipients")

    token = secrets.token_urlsafe(32)[:64]
    row = DealParticipant(
        deal_id=deal_id,
        user_id=None,
        role=DealParticipantRole.recipient,
        invited_by=current_user.id,
        invite_token=token,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return InviteOut(
        id=row.id,
        deal_id=row.deal_id,
        role=row.role.value,
        invite_token=token,
        invite_url=_invite_url(token),
        invited_at=row.invited_at,
    )


@router.post("/deals/join/{token}")
async def accept_deal_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach the current authenticated user to a pending invite.

    Idempotent — accepting twice with the same user is a no-op (returns the
    same row). Accepting a token that's already bound to another user is 409.
    """
    row = (
        await db.execute(
            select(DealParticipant).where(DealParticipant.invite_token == token)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if row.revoked_at is not None:
        raise HTTPException(status_code=410, detail="Invite revoked")

    if row.user_id is not None and row.user_id != current_user.id:
        raise HTTPException(status_code=409, detail="Invite already claimed by another user")

    # Deal sender/carrier can't be recipient — they already have access.
    deal = await db.get(Deal, row.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id in (deal.sender_id, deal.carrier_id):
        raise HTTPException(
            status_code=400,
            detail="You are already a principal participant of this deal",
        )

    if row.user_id is None:
        row.user_id = current_user.id
        row.accepted_at = datetime.now(tz=timezone.utc)
        await db.commit()
    return {"deal_id": str(row.deal_id), "role": row.role.value}


@router.post("/deals/{deal_id}/participants/{user_id}/revoke")
async def revoke_participant(
    deal_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sender revokes an invited recipient. Past messages remain readable
    (revocation cannot erase what already reached the recipient); new e2e
    messages won't include their read_package."""
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only sender can revoke")

    row = (
        await db.execute(
            select(DealParticipant).where(
                DealParticipant.deal_id == deal_id,
                DealParticipant.user_id == user_id,
                DealParticipant.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No active participant to revoke")
    row.revoked_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return {"revoked": True}


@router.get("/deals/{deal_id}/participants", response_model=list[ParticipantOut])
async def list_participants(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active recipients of a deal. Anyone with deal access can see them
    (needed by e2e write path to include their npubs in read_packages)."""
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Access = sender / carrier / already-attached participant.
    from app.models.deal import DealParticipant as DP  # local alias

    if current_user.id not in (deal.sender_id, deal.carrier_id):
        own_row = (
            await db.execute(
                select(DP).where(
                    DP.deal_id == deal_id,
                    DP.user_id == current_user.id,
                    DP.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if own_row is None:
            raise HTTPException(status_code=403, detail="Not a deal participant")

    rows = (
        await db.execute(
            select(DP, User)
            .join(User, DP.user_id == User.id, isouter=True)
            .where(DP.deal_id == deal_id, DP.revoked_at.is_(None))
        )
    ).all()
    return [
        ParticipantOut(
            id=p.id,
            deal_id=p.deal_id,
            user_id=p.user_id,
            display_name=(u.display_name if u else None),
            npub=(u.nostr_pubkey if u else None),
            role=p.role.value if hasattr(p.role, "value") else str(p.role),
            invited_at=p.invited_at,
            accepted_at=p.accepted_at,
        )
        for (p, u) in rows
    ]
