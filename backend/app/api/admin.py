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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, is_superuser
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.core.permissions import Permission, require_perm
from app.core.deal_chain import append_deal_event, content_hash_of
from app.core.signing import sign_vault_message
from app.models.deal import (
    Attachment,
    Deal,
    DealChainAnchor,
    DealEvent,
    DealEventType,
    DealStatus,
    DealVaultMessage,
    Dispute,
    DisputeStatus,
    OperatorAccessGrant,
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
    await db.flush()

    # T3.2 — opener implicitly consents to arbiter reading DealVault.
    db.add(OperatorAccessGrant(dispute_id=dispute.id, granted_by=current_user.id))

    deal.status = DealStatus.disputed
    # T3.7 — a dispute may open after closing (problems surface post-confirm);
    # `dispute_opened` is the one event type the seal guard admits, and it
    # unseals the vault so evidence can be appended. The chain records both
    # the seal and this unseal — nothing is hidden.
    deal.sealed_at = None
    await append_deal_event(
        db,
        deal_id=deal_id,
        event_type=DealEventType.dispute_opened,
        actor_id=current_user.id,
        payload={"reason": body.reason.strip()[:200]},
        author=current_user,
    )

    await db.commit()
    await db.refresh(dispute)
    return dispute


@router.post("/disputes/{dispute_id}/grant-access", response_model=DisputeOut)
async def grant_arbiter_access(
    dispute_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.2 — the counterparty of a dispute may add their own access grant so
    the arbiter can inspect the DealVault with two-sided consent on record.

    Idempotent: re-granting after a revoke re-activates the row instead of
    inserting a duplicate (UNIQUE(dispute_id, granted_by))."""
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    deal = await db.get(Deal, dispute.deal_id)
    if deal is None or current_user.id not in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Not a deal participant")

    existing = await db.execute(
        select(OperatorAccessGrant).where(
            OperatorAccessGrant.dispute_id == dispute_id,
            OperatorAccessGrant.granted_by == current_user.id,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(OperatorAccessGrant(dispute_id=dispute_id, granted_by=current_user.id))
    else:
        row.revoked_at = None
    await db.commit()
    return dispute


@router.post("/disputes/{dispute_id}/revoke-access", response_model=DisputeOut)
async def revoke_arbiter_access(
    dispute_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.2 — participant may revoke their earlier grant. Arbiter can still
    read if the other participant's grant remains active."""
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    row_result = await db.execute(
        select(OperatorAccessGrant).where(
            OperatorAccessGrant.dispute_id == dispute_id,
            OperatorAccessGrant.granted_by == current_user.id,
        )
    )
    row = row_result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No grant to revoke")
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return dispute


@router.get("/admin/disputes", response_model=Page[DisputeOut])
async def list_disputes(
    current_user: User = Depends(require_perm(Permission.DISPUTE_LIST_ADMIN)),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    base = select(Dispute)
    # Non-superuser arbiter sees only unclaimed disputes and their own claimed ones
    if not is_superuser(current_user):
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
    current_user: User = Depends(require_perm(Permission.DISPUTE_CLAIM)),
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
    current_user: User = Depends(require_perm(Permission.DISPUTE_RESOLVE)),
    db: AsyncSession = Depends(get_db),
):
    dispute = await db.get(Dispute, dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if dispute.arbiter_id != current_user.id and not is_superuser(current_user):
        raise HTTPException(status_code=403, detail="You didn't claim this dispute")

    dispute.status = DisputeStatus.resolved
    dispute.verdict = body.verdict
    dispute.resolved_at = datetime.now(timezone.utc)

    deal = await db.get(Deal, dispute.deal_id)
    if deal:
        await append_deal_event(
            db,
            deal_id=deal.id,
            event_type=DealEventType.dispute_resolved,
            actor_id=current_user.id,
            payload={"verdict": body.verdict[:500]},
            author=current_user,
        )
        if body.closes_deal:
            deal.status = DealStatus.closed
            # T3.7 — a closing verdict re-seals the vault (mirror of
            # confirm_deal): seal event first, then `sealed_at`.
            message_count = (
                await db.execute(
                    select(func.count())
                    .select_from(DealVaultMessage)
                    .where(DealVaultMessage.deal_id == deal.id)
                )
            ).scalar_one()
            file_count = (
                await db.execute(
                    select(func.count())
                    .select_from(Attachment)
                    .join(
                        DealVaultMessage,
                        Attachment.message_id == DealVaultMessage.id,
                    )
                    .where(DealVaultMessage.deal_id == deal.id)
                )
            ).scalar_one()
            await append_deal_event(
                db,
                deal_id=deal.id,
                event_type=DealEventType.sealed,
                actor_id=current_user.id,
                payload={
                    "message_count": message_count,
                    "file_count": file_count,
                },
                author=current_user,
            )
            deal.sealed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(dispute)
    return dispute


# ─────────────────────────────────────────────────────────────
# Arbiter reads DealVault only for claimed dispute + audits
# ─────────────────────────────────────────────────────────────


@router.get("/admin/deals/{deal_id}/vault", response_model=Page[MessageOut])
async def arbiter_read_vault(
    deal_id: uuid.UUID,
    current_user: User = Depends(require_perm(Permission.VAULT_READ_AS_ARBITER)),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
):
    dispute_result = await db.execute(
        select(Dispute).where(Dispute.deal_id == deal_id)
    )
    dispute = dispute_result.scalar_one_or_none()

    # Access requires a claimed dispute by this arbiter (superuser bypasses)
    if not is_superuser(current_user):
        if not dispute:
            raise HTTPException(status_code=403, detail="No dispute for this deal")
        if dispute.arbiter_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your claimed dispute")
        if dispute.status not in (DisputeStatus.claimed, DisputeStatus.resolved):
            raise HTTPException(status_code=403, detail="Dispute not claimed")
        # T3.2 — at least one active OperatorAccessGrant must exist.
        active_grant = await db.execute(
            select(OperatorAccessGrant).where(
                OperatorAccessGrant.dispute_id == dispute.id,
                OperatorAccessGrant.revoked_at.is_(None),
            )
        )
        if active_grant.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=403,
                detail="No active access grant — both parties revoked consent",
            )

    # Audit trail: DealEvent + system-message in the chat. `arbiter_opened` is
    # chained even on a sealed vault (audit events pass the seal guard); the
    # chat system-message is content, so it is skipped once sealed (T3.7).
    now = datetime.now(timezone.utc)
    await append_deal_event(
        db,
        deal_id=deal_id,
        event_type=DealEventType.arbiter_opened,
        actor_id=current_user.id,
        payload={"dispute_id": str(dispute.id) if dispute else None, "at": now.isoformat()},
        author=current_user,
    )
    deal = await db.get(Deal, deal_id)
    if deal is not None and deal.sealed_at is None:
        dispute_ref = f"#{str(dispute.id)[:8]}" if dispute else "(direct)"
        sys_msg = DealVaultMessage(
            deal_id=deal_id,
            sender_id=None,  # system message; nostr_sig stays None
            text=f"⚖️ Arbiter opened conversation for dispute {dispute_ref}",
            is_system=True,
        )
        db.add(sys_msg)
        # T3.7 — chain the system message like any other vault content.
        await db.flush()
        await append_deal_event(
            db,
            deal_id=deal_id,
            event_type=DealEventType.message_added,
            actor_id=current_user.id,
            payload={
                "message_id": str(sys_msg.id),
                "content_hash": content_hash_of(
                    sys_msg.text_ciphertext, sys_msg.text_nonce
                ),
                "msg_event_id": sys_msg.nostr_event_id,
                "is_e2e": False,
            },
            author=current_user,
        )
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
    _: User = Depends(require_perm(Permission.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    email_contains: str | None = Query(
        default=None,
        description="Optional substring filter on email. Case-insensitive.",
    ),
):
    """T_TEST.3 — `email_contains` lets superuser find e2e test users
    (`@e2e.vimana.local`) or otherwise scope the list without pulling
    thousands of rows."""
    base = select(User)
    if email_contains:
        base = base.where(User.email.ilike(f"%{email_contains}%"))
    items, next_cursor = await paginate_desc(db, base, User, after, clamp_limit(limit))
    return Page(items=items, next_cursor=next_cursor)


class PromoteBody(BaseModel):
    is_arbiter: bool


@router.post("/admin/users/{user_id}/promote-arbiter", response_model=UserOut)
async def promote_arbiter(
    user_id: uuid.UUID,
    body: PromoteBody,
    _: User = Depends(require_perm(Permission.ARBITER_ASSIGN)),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superuser":
        raise HTTPException(status_code=400, detail="Cannot demote superuser")
    user.role = "arbiter" if body.is_arbiter else "user"
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_perm(Permission.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """T_TEST.3 — superuser hard-delete for e2e/junk cleanup.

    Runs the same cascade as `cleanup_e2e_users` (see `app/tasks/cleanup.py`)
    but for a single user on demand. Superuser cannot delete themselves or
    another superuser.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Self-check first — more actionable than the superuser message when both
    # apply (admin trying to delete themselves).
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    if user.role == "superuser":
        raise HTTPException(status_code=400, detail="Cannot delete a superuser")

    # Async cascade — mirrors the sync cleanup in `app/tasks/cleanup.py`.
    # Keep in sync when the schema grows.
    from sqlalchemy import delete
    from app.models.deal import (
        Attachment,
        Deal,
        DealParticipant,
        DealVaultMessage,
        Dispute,
        OperatorAccessGrant,
    )
    from app.models.marketplace import InquiryMessage, Order, Trip, TripInquiry
    from app.models.social import Connection, InviteLink
    from app.models.trust import TrustEdge

    ids = [user_id]
    trip_ids = [
        r[0] for r in (await db.execute(select(Trip.id).where(Trip.carrier_id.in_(ids)))).all()
    ]
    deal_ids = [
        r[0]
        for r in (
            await db.execute(
                select(Deal.id).where(
                    (Deal.sender_id.in_(ids)) | (Deal.carrier_id.in_(ids))
                )
            )
        ).all()
    ]
    if deal_ids:
        msg_ids = [
            r[0]
            for r in (
                await db.execute(
                    select(DealVaultMessage.id).where(
                        DealVaultMessage.deal_id.in_(deal_ids)
                    )
                )
            ).all()
        ]
        if msg_ids:
            await db.execute(delete(Attachment).where(Attachment.message_id.in_(msg_ids)))
        await db.execute(delete(DealVaultMessage).where(DealVaultMessage.deal_id.in_(deal_ids)))
        await db.execute(delete(DealEvent).where(DealEvent.deal_id.in_(deal_ids)))
        # T3.6 — anchors FK to deals; drop them before the deal rows.
        await db.execute(
            delete(DealChainAnchor).where(DealChainAnchor.deal_id.in_(deal_ids))
        )
        dispute_ids = [
            r[0]
            for r in (
                await db.execute(select(Dispute.id).where(Dispute.deal_id.in_(deal_ids)))
            ).all()
        ]
        if dispute_ids:
            await db.execute(
                delete(OperatorAccessGrant).where(
                    OperatorAccessGrant.dispute_id.in_(dispute_ids)
                )
            )
            await db.execute(delete(Dispute).where(Dispute.id.in_(dispute_ids)))
        await db.execute(
            delete(DealParticipant).where(DealParticipant.deal_id.in_(deal_ids))
        )
        await db.execute(delete(Deal).where(Deal.id.in_(deal_ids)))
    if trip_ids:
        inquiry_ids = [
            r[0]
            for r in (
                await db.execute(
                    select(TripInquiry.id).where(TripInquiry.trip_id.in_(trip_ids))
                )
            ).all()
        ]
        if inquiry_ids:
            await db.execute(
                delete(InquiryMessage).where(InquiryMessage.inquiry_id.in_(inquiry_ids))
            )
            await db.execute(delete(TripInquiry).where(TripInquiry.id.in_(inquiry_ids)))
        await db.execute(delete(Trip).where(Trip.id.in_(trip_ids)))
    await db.execute(
        delete(TrustEdge).where(
            (TrustEdge.from_user_id.in_(ids)) | (TrustEdge.to_user_id.in_(ids))
        )
    )
    await db.execute(
        delete(Connection).where(
            (Connection.user_id.in_(ids)) | (Connection.connected_user_id.in_(ids))
        )
    )
    await db.execute(
        delete(InviteLink).where(
            (InviteLink.creator_id.in_(ids)) | (InviteLink.used_by.in_(ids))
        )
    )
    await db.execute(delete(Order).where(Order.sender_id.in_(ids)))
    await db.execute(delete(User).where(User.id.in_(ids)))
    await db.commit()
    return


class ScanQueueOut(BaseModel):
    """T3.8 — how many stored files nobody has looked at yet.

    Exists because the Telegram alert is a moment and this is a state. An alert
    that arrives while nobody is at the keyboard is gone; a counter is still
    here tomorrow, and the number climbing is the signal that matters more than
    any single outage.

    `scanner_configured` is included so the page can tell two very different
    situations apart: a queue that is draining, and a queue that will never
    drain because no scanner exists.
    """

    pending: int
    infected: int
    clean: int
    scanner_configured: bool


@router.get("/admin/scan-queue", response_model=ScanQueueOut)
async def scan_queue(
    _: User = Depends(require_perm(Permission.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    from app.core.file_validation import _clamav_target
    from app.models.deal import Attachment

    rows = (
        await db.execute(
            select(Attachment.scan_status, func.count()).group_by(Attachment.scan_status)
        )
    ).all()
    counts = {status: int(n) for status, n in rows}
    return ScanQueueOut(
        pending=counts.get("pending", 0),
        infected=counts.get("infected", 0),
        clean=counts.get("clean", 0),
        scanner_configured=_clamav_target() is not None,
    )
