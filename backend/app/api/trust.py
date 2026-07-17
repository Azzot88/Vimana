"""T2.4 — Trust Graph HTTP endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.trust import bfs_circles, distance_between
from app.models.trust import TrustEdgeKind
from app.models.user import User

router = APIRouter()


class TrustCirclesOut(BaseModel):
    depth: int
    kind: str | None
    circles: dict[str, list[uuid.UUID]]  # {"1": [...], "2": [...]}
    total_reachable: int


class TrustMetricsOut(BaseModel):
    subject_id: uuid.UUID
    verifications_issued_count: int
    verifications_received_count: int
    dealt_with_count: int
    distance_from_viewer: int | None  # None if not authenticated or not connected


@router.get("/me/trust-circle", response_model=TrustCirclesOut)
async def my_trust_circle(
    depth: int = Query(3, ge=1, le=6),
    kind: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed_kind = None
    if kind:
        try:
            parsed_kind = TrustEdgeKind(kind)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"kind must be one of: {[k.value for k in TrustEdgeKind]}",
            )
    levels = await bfs_circles(
        db, root_id=current_user.id, depth=depth, kind=parsed_kind
    )
    # Skip level 0 (self) from output; keep 1..depth.
    circles_out = {str(k): v for k, v in levels.items() if k > 0}
    total = sum(len(v) for v in circles_out.values())
    return TrustCirclesOut(
        depth=depth,
        kind=parsed_kind.value if parsed_kind else None,
        circles=circles_out,
        total_reachable=total,
    )


@router.get("/users/{user_id}/trust-metrics", response_model=TrustMetricsOut)
async def user_trust_metrics(
    user_id: uuid.UUID,
    current_user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    distance: int | None = None
    if current_user is not None and current_user.id != user_id:
        distance = await distance_between(
            db, root_id=current_user.id, target_id=user_id, max_depth=6
        )

    return TrustMetricsOut(
        subject_id=user_id,
        verifications_issued_count=user.verifications_issued_count,
        verifications_received_count=user.verifications_received_count,
        dealt_with_count=user.dealt_with_count,
        distance_from_viewer=distance,
    )
