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


class RecipientBody(BaseModel):
    """T3.11.24 — one of two ways to name a recipient who already has an account.

    From the contacts list you have their id; from a pasted key you have the
    key. The third path in the owner's brief — a service link — is
    `invite-recipient` above, and it is deliberately *not* merged into this
    endpoint: it produces a link for somebody who is not on the platform yet,
    and pretending the three ways are equivalent is exactly what the form must
    not do.
    """

    user_id: uuid.UUID | None = None
    npub: str | None = None


@router.post("/deals/{deal_id}/recipient", response_model=ParticipantOut, status_code=201)
async def set_recipient(
    deal_id: uuid.UUID,
    body: RecipientBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sender-only: attach a recipient who is already on the platform.

    No token, no waiting: the person exists, so the participant row is written
    already accepted and `Deal.recipient_id` is filled. That column was never
    set by the invite path — the recipient there is a `DealParticipant` and
    nothing else — and a deal whose recipient is known should say so where
    everything else reads it.

    A key that belongs to nobody is a `404` with a detail the form can show. It
    is not an invitation in disguise: the sender asked to attach *this* person,
    and quietly issuing a link instead would leave them believing the recipient
    is attached when nobody has accepted anything.
    """
    if (body.user_id is None) == (body.npub is None):
        raise HTTPException(
            status_code=422, detail="Give exactly one of user_id or npub"
        )

    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only sender can set the recipient")

    if body.user_id is not None:
        person = await db.get(User, body.user_id)
    else:
        person = (
            await db.execute(
                select(User).where(User.nostr_pubkey == body.npub.strip())
            )
        ).scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status_code=404, detail="No account for that person — send an invite instead"
        )
    if person.id in (deal.sender_id, deal.carrier_id):
        raise HTTPException(
            status_code=400,
            detail="They are already a principal participant of this deal",
        )

    existing = (
        await db.execute(
            select(DealParticipant).where(
                DealParticipant.deal_id == deal_id,
                DealParticipant.user_id == person.id,
                DealParticipant.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    row = existing or DealParticipant(
        deal_id=deal_id,
        user_id=person.id,
        role=DealParticipantRole.recipient,
        invited_by=current_user.id,
        accepted_at=datetime.now(tz=timezone.utc),
    )
    if existing is None:
        db.add(row)
    deal.recipient_id = person.id
    await db.commit()
    await db.refresh(row)
    return ParticipantOut(
        id=row.id,
        deal_id=row.deal_id,
        user_id=row.user_id,
        display_name=person.display_name,
        npub=person.nostr_pubkey,
        role=row.role.value,
        invited_at=row.invited_at,
        accepted_at=row.accepted_at,
    )
