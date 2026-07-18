"""T3.1 — read endpoints for УБА."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import SyncSessionLocal, get_db
from app.core.uba import (
    UBAComponents,
    compute_components,
    compute_uba,
    level_of,
    recompute_and_persist,
)
from app.models.user import User

router = APIRouter()


def _compute_sync(user_id: uuid.UUID) -> tuple[UBAComponents, int]:
    """Bridge to the sync Celery-style session for on-demand recompute.

    The formula walks tens of rows per call — cheap even without cache. Once
    per-user hit rate rises we'll add a Redis TTL wrapper.
    """
    with SyncSessionLocal() as db:
        components = compute_components(db, user_id)
        score = compute_uba(components)
        return components, score


@router.get("/users/{user_id}/uba")
async def get_user_uba(
    user_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    components, score = _compute_sync(user_id)
    # Refresh the cached column too so profile reads pick up the fresh value.
    with SyncSessionLocal() as sync_db:
        recompute_and_persist(sync_db, user_id)

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
