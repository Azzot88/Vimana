"""T1.23 — admin & arbiter endpoints.

Access model:
- User Zero (superuser) sees everything and promotes arbiters.
- Arbiter sees only disputes assigned to them; reads DealVault only for a
  claimed dispute. Each vault read logs `arbiter_opened` + system-message.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_arbiter, get_current_user, get_superuser
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.models.deal import (
    Deal,
    DealEvent,
    DealEventType,
    DealStatus,
    DealVaultMessage,
    Dispute,
    DisputeStatus,
)
from app.models.user import User
from app.schemas.dealvault import MessageOut
from app.schemas.user import UserOut

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# Disputes: opened by participants, claimed/resolved by arbiter
# ─────────────────────────────────────────────────────────────


class DisputeCreate(BaseModel):
    reason: str


class DisputeOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    opened_by: uuid.UUID
    arbiter_id: uuid.UUID | None
    reason: str
    status: str
    verdict: str | None
    created_at: datetime
    resolved_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class ResolveBody(BaseModel):
    verdict: str
    closes_deal: bool = False


@router.post("/deals/{deal_id}/dispute", response_model=DisputeOut, status_code=201)
async def open_dispute(
    deal_id: uuid.UUID,
    body: DisputeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id not in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Only deal participants can open a dispute")

    existing = await db.execute(select(Dispute).where(Dispute.deal_id == deal_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Dispute already exists for this deal")

    dispute = Dispute(
        deal_id=deal_id,
        opened_by=current_user.id,
        reason=body.reason.strip(),
        status=DisputeStatus.open,
    )
    db.add(dispute)

    deal.status = DealStatus.disputed
    db.add(DealEvent(
        deal_id=deal_id,
        event_type=DealEventType.dispute_opened,
        actor_id=current_user.id,
        payload={"reason": body.reason.strip()[:200]},
    ))

    await db.commit()
    await db.refresh(dispute)
    return dispute


@router.get("/admin/disputes", response_model=Page[DisputeOut])
async def list_disputes(
    current_user: User = Depends(get_arbiter),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    base = select(Dispute)
    # Non-superuser arbiter sees only unclaimed disputes and their own claimed ones
    if not current_user.is_superuser:
        from sqlalchemy import or_
        base = base.where(
            or_(
                Dispute.status == DisputeStatus.open,
                Dispute.arbiter_id == current_user.id,
            )
        )
    items, next_cursor = await paginate_desc(db, base, Dispute, after, clamp_limit(limit))
    return Page(items=items, next_cursor=next_cursor)


@router.post("/disputes/{dispute_id}/claim", response_model=DisputeOut)
async def claim_dispute(
    dispute_id: uuid.UUID,
    current_user: User = Depends(get_arbiter),
    db: AsyncSession = Depends(get_db),
):
    dispute = await db.get(Dispute, dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    # Arbiter cannot judge own deal
    deal = await db.get(Deal, dispute.deal_id)
    if deal and current_user.id in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Cannot judge your own deal")

    if dispute.status != DisputeStatus.open:
        raise HTTPException(status_code=409, detail="Dispute is not open")

    dispute.arbiter_id = current_user.id
    dispute.status = DisputeStatus.claimed
    await db.commit()
    await db.refresh(dispute)
    return dispute


@router.post("/disputes/{dispute_id}/resolve", response_model=DisputeOut)
async def resolve_dispute(
    dispute_id: uuid.UUID,
    body: ResolveBody,
    current_user: User = Depends(get_arbiter),
    db: AsyncSession = Depends(get_db),
):
    dispute = await db.get(Dispute, dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if dispute.arbiter_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="You didn't claim this dispute")

    dispute.status = DisputeStatus.resolved
    dispute.verdict = body.verdict
    dispute.resolved_at = datetime.now(timezone.utc)

    deal = await db.get(Deal, dispute.deal_id)
    if deal:
        db.add(DealEvent(
            deal_id=deal.id,
            event_type=DealEventType.dispute_resolved,
            actor_id=current_user.id,
            payload={"verdict": body.verdict[:500]},
        ))
        if body.closes_deal:
            deal.status = DealStatus.closed

    await db.commit()
    await db.refresh(dispute)
    return dispute


# ─────────────────────────────────────────────────────────────
# Arbiter reads DealVault only for claimed dispute + audits
# ─────────────────────────────────────────────────────────────


@router.get("/admin/deals/{deal_id}/vault", response_model=Page[MessageOut])
async def arbiter_read_vault(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_arbiter),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
):
    dispute_result = await db.execute(
        select(Dispute).where(Dispute.deal_id == deal_id)
    )
    dispute = dispute_result.scalar_one_or_none()

    # Access requires a claimed dispute by this arbiter (superuser bypasses)
    if not current_user.is_superuser:
        if not dispute:
            raise HTTPException(status_code=403, detail="No dispute for this deal")
        if dispute.arbiter_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your claimed dispute")
        if dispute.status not in (DisputeStatus.claimed, DisputeStatus.resolved):
            raise HTTPException(status_code=403, detail="Dispute not claimed")

    # Audit trail: DealEvent + system-message in the chat
    now = datetime.now(timezone.utc)
    db.add(DealEvent(
        deal_id=deal_id,
        event_type=DealEventType.arbiter_opened,
        actor_id=current_user.id,
        payload={"dispute_id": str(dispute.id) if dispute else None, "at": now.isoformat()},
    ))
    dispute_ref = f"#{str(dispute.id)[:8]}" if dispute else "(direct)"
    db.add(DealVaultMessage(
        deal_id=deal_id,
        sender_id=None,
        text=f"⚖️ Arbiter opened conversation for dispute {dispute_ref}",
        is_system=True,
    ))
    await db.commit()

    stmt = (
        select(DealVaultMessage)
        .where(DealVaultMessage.deal_id == deal_id)
        .options(selectinload(DealVaultMessage.attachments))
    )
    from app.core.pagination import paginate_asc
    from app.api.dealvault import _build_message_out
    items, next_cursor = await paginate_asc(
        db, stmt, DealVaultMessage, after, clamp_limit(limit)
    )
    return Page(items=[_build_message_out(m) for m in items], next_cursor=next_cursor)


# ─────────────────────────────────────────────────────────────
# User admin (superuser only)
# ─────────────────────────────────────────────────────────────


@router.get("/admin/users", response_model=Page[UserOut])
async def list_users(
    _: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    base = select(User)
    # User doesn't have `created_at` as pagination cursor field? It does — check.
    items, next_cursor = await paginate_desc(db, base, User, after, clamp_limit(limit))
    return Page(items=items, next_cursor=next_cursor)


class PromoteBody(BaseModel):
    is_arbiter: bool


@router.post("/admin/users/{user_id}/promote-arbiter", response_model=UserOut)
async def promote_arbiter(
    user_id: uuid.UUID,
    body: PromoteBody,
    _: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_arbiter = body.is_arbiter
    await db.commit()
    await db.refresh(user)
    return user
