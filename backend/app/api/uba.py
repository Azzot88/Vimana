"""T3.1 — read endpoints for УБА.

Uses the async session so the API sees the same DB the request-scoped code
sees. Celery beat has its own sync-session path in `core.uba` /
`tasks.uba`; keep the two aligned but don't share sessions.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.permissions import require_visible
from app.core.uba import (
    UBAComponents,
    WINDOW_DAYS,
    _VERIFY_FACTOR,
    _VERIFY_FACTOR_MAX,
    compute_uba,
    level_of,
)
from app.models.deal import (
    Attachment,
    AttachmentKind,
    Deal,
    DealStatus,
    DealVaultMessage,
)
from app.models.marketplace import Order
from app.models.user import User

router = APIRouter()


async def _compute_components_async(
    db: AsyncSession, user_id: uuid.UUID
) -> UBAComponents:
    """Async twin of `core.uba.compute_components` — same formula, async I/O.

    Refactoring the shared logic into query builders would let the two share
    code, but the payoff is small: five queries, all trivial. Duplication is
    kept intentionally minimal (same enums, same window constant, same field
    semantics)."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=WINDOW_DAYS)

    f_count = (
        await db.execute(
            select(func.count(Deal.id)).where(
                Deal.carrier_id == user_id,
                Deal.status == DealStatus.closed,
                Deal.created_at >= since,
            )
        )
    ).scalar() or 0

    v_sum = (
        await db.execute(
            select(func.coalesce(func.sum(Order.declared_value), 0.0))
            .select_from(Deal)
            .join(Order, Order.id == Deal.order_id)
            .where(
                Deal.carrier_id == user_id,
                Deal.status == DealStatus.closed,
                Deal.created_at >= since,
            )
        )
    ).scalar() or 0.0

    handoff_exists = (
        select(1)
        .select_from(Attachment)
        .join(DealVaultMessage, Attachment.message_id == DealVaultMessage.id)
        .where(
            DealVaultMessage.deal_id == Deal.id,
            Attachment.kind == AttachmentKind.handoff_photo,
        )
        .exists()
    )
    receipt_exists = (
        select(1)
        .select_from(Attachment)
        .join(DealVaultMessage, Attachment.message_id == DealVaultMessage.id)
        .where(
            DealVaultMessage.deal_id == Deal.id,
            Attachment.kind == AttachmentKind.receipt_photo,
        )
        .exists()
    )
    q_count = (
        await db.execute(
            select(func.count(Deal.id)).where(
                Deal.carrier_id == user_id,
                Deal.status == DealStatus.closed,
                Deal.created_at >= since,
                handoff_exists,
                receipt_exists,
            )
        )
    ).scalar() or 0

    verify_level = (
        await db.execute(
            select(User.highest_verification_level).where(User.id == user_id)
        )
    ).scalar()

    return UBAComponents(
        f_count=int(f_count),
        q_count=int(q_count),
        v_sum=float(v_sum),
        d_peak=0.0,
        verify_level=verify_level,
    )


@router.get("/users/{user_id}/uba")
async def get_user_uba(
    user_id: uuid.UUID,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # T3.18 — one gate, called from every public slice (`core.permissions`).
    require_visible(user, viewer)

    components = await _compute_components_async(db, user_id)
    score = compute_uba(components)
    # Refresh cache column too so profile reads pick up the fresh value.
    user.business_activity_level = float(score)
    await db.commit()

    return {
        "user_id": str(user_id),
        "uba": score,
        "level": level_of(score),
        "components": {
            "f_count": components.f_count,
            "q_count": components.q_count,
            "v_sum": components.v_sum,
            "d_peak": components.d_peak,
            "verify_level": components.verify_level,
        },
    }


@router.get("/me/uba")
async def get_my_uba(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_uba(current_user.id, current_user, db)
