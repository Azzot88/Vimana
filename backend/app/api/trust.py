"""T2.4 — Trust Graph HTTP endpoints, plus the public identity page (T3.18)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.database import get_db
from app.core.permissions import require_visible
from app.core.storage import get_presigned_url
from app.core.trust import bfs_circles, distance_between
from app.core.uba import level_of
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
    # T3.18 — optional, which is what the annotation always claimed:
    # `get_current_user` never returns None, so an anonymous caller got a 401
    # from a signature that said the viewer might be absent. These are the same
    # counters the public identity page shows, so requiring a session here and
    # not there was a difference without a reason. Anonymous simply gets no
    # `distance_from_viewer` — there is no viewer to measure from.
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # T3.18 — the same gate as the identity page. Without it `hidden` would hide
    # the page and leave the numbers on it readable one URL over.
    require_visible(user, current_user)

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


# ─────────────────────────────────────────────────────────────
# T3.18 — the public identity page
# ─────────────────────────────────────────────────────────────


class IdentityOut(BaseModel):
    """What a stranger may learn about an identity.

    Addressed by **npub**, not by the internal id: the key *is* the identity
    (`D-KEY-TIERS`), and the row id is an implementation detail that has no
    business in a shareable link.

    Never here, at any visibility level: email, phone, receiving addresses,
    anything from inside a vault. Those are not "private fields of a profile",
    they are a different category of data.
    """

    npub: str
    visibility: str
    display_name: str | None = None
    avatar_url: str | None = None
    member_since: datetime | None = None
    uba: int | None = None
    uba_level: str | None = None
    highest_verification_level: str | None = None
    verifications_issued_count: int | None = None
    verifications_received_count: int | None = None
    dealt_with_count: int | None = None
    key_lost: bool = False
    # T3.23 — a key swap is public information: everything signed before it
    # stays signed by a key this identity no longer holds, and a counterparty
    # weighing old evidence deserves the date rather than a surprise.
    identity_changed_at: datetime | None = None
    previous_npub: str | None = None


@router.get("/identities/{npub}", response_model=IdentityOut)
async def public_identity(
    npub: str,
    viewer: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Open an identity by its key. No account required to look.

    A marketplace where nobody can look anybody up is a marketplace where
    nobody deals, so this is readable without signing in — and everything on it
    is already public elsewhere in the product. What is new is that it is in one
    place and has an address.
    """
    key = (npub or "").strip().lower()
    subject = (
        await db.execute(select(User).where(User.nostr_pubkey == key))
    ).scalars().first()
    if subject is None:
        raise HTTPException(status_code=404, detail="No such identity")

    level = require_visible(subject, viewer)

    if level == "minimal":
        # Existence and how well proven it is — enough to answer "is this key a
        # real participant" without drawing a portrait.
        return IdentityOut(
            npub=key,
            visibility=level,
            highest_verification_level=subject.highest_verification_level,
            key_lost=subject.key_lost,
        )

    uba = (
        int(subject.business_activity_level)
        if subject.business_activity_level is not None
        else None
    )
    return IdentityOut(
        npub=key,
        visibility=level,
        display_name=subject.display_name,
        avatar_url=get_presigned_url(subject.avatar_key) if subject.avatar_key else None,
        member_since=subject.created_at,
        uba=uba,
        uba_level=level_of(uba) if uba is not None else None,
        highest_verification_level=subject.highest_verification_level,
        verifications_issued_count=subject.verifications_issued_count,
        verifications_received_count=subject.verifications_received_count,
        dealt_with_count=subject.dealt_with_count,
        key_lost=subject.key_lost,
        identity_changed_at=subject.identity_changed_at,
        previous_npub=subject.previous_nostr_pubkey,
    )
