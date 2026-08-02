"""T3.1 — Уровень Бизнес-Активности (УБА).

Pure computation of the trust score per IMPLEMENTATIONPLAN §6 §3.1:

    F_norm         = min(F / 8, 1.0)
    Q_norm         = min(log10(Q + 1) / log10(51), 1.0)
    V_norm         = min(log10(V + 1) / log10(50001), 1.0)
    D_factor       = 1.0 + 0.5 × min(D / 5000, 1.0)          # [1.0 … 1.5]
    V_verify_norm  = V_verify_factor / 1.30                   # [~0.77 … 1.0]

    УБА = round(F_norm × Q_norm × V_norm × D_factor × V_verify_norm × 1000)

Rolling 90-day window for F/Q/V. F is monthly rate (deals ÷ 3 months). Q counts
only deals with **both** DealVault photos (handoff + receipt). D is the peak
active collateral — not implemented yet (Collateral model is Phase 5). Verification
factor comes from T2.1 `User.highest_verification_level`.

Public API:
- `compute_components(db_sync, user_id)` → `UBAComponents` (raw counters).
- `compute_uba(components)` → int in [0, 1000].
- `level_of(uba)` → level slug from `LEVELS`.

Sync DB session (Celery worker uses `SyncSessionLocal`), no async here.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deal import (
    Attachment,
    AttachmentKind,
    Deal,
    DealStatus,
    DealVaultMessage,
)
from app.core.freshness import freshness_factor
from app.models.marketplace import Order
from app.models.user import User
from app.models.verification import VerificationBadge

WINDOW_DAYS = 90

# Verification factor per T2.1 highest_verification_level. Keep in sync with
# `VerificationLevel` enum values in `app.models.verification`.
_VERIFY_FACTOR = {
    None: 1.00,
    "auto": 1.05,
    "peer": 1.15,
    "kyc": 1.30,
}
_VERIFY_FACTOR_MAX = 1.30

# UBA -> level slug. Slugs are stable; localisation happens at UI layer.
LEVELS: list[tuple[int, str]] = [
    (0, "newbie"),
    (50, "verified"),
    (200, "reliable"),
    (450, "trusted"),
    (750, "elite"),
]


@dataclass(frozen=True)
class UBAComponents:
    f_count: int      # closed deals as carrier in window
    q_count: int      # closed deals with both DealVault photos
    v_sum: float      # sum of Order.declared_value on closed deals
    d_peak: float     # peak active collateral (0 until T5.x Collateral model)
    verify_level: str | None  # highest_verification_level
    # T_TRUST.1 — when the badge behind that level was issued. None means either
    # no verification at all or one with no date, and `freshness_factor` treats
    # the second case as the floor rather than as fresh.
    verify_at: datetime | None = None


def _window_start() -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=WINDOW_DAYS)


def compute_components(db: Session, user_id: uuid.UUID) -> UBAComponents:
    """Snapshot the raw metrics for one user over the rolling window."""
    since = _window_start()

    # F — closed deals where user is the carrier (delivery = work performed).
    f_count = db.execute(
        select(func.count(Deal.id)).where(
            Deal.carrier_id == user_id,
            Deal.status == DealStatus.closed,
            Deal.created_at >= since,
        )
    ).scalar() or 0

    # V — sum of declared_value on closed deals (as carrier).
    v_sum = db.execute(
        select(func.coalesce(func.sum(Order.declared_value), 0.0))
        .select_from(Deal)
        .join(Order, Order.id == Deal.order_id)
        .where(
            Deal.carrier_id == user_id,
            Deal.status == DealStatus.closed,
            Deal.created_at >= since,
        )
    ).scalar() or 0.0

    # Q — closed deals with BOTH handoff_photo AND receipt_photo attachments in
    # DealVault. Two exists() sub-queries per deal are cheap enough for hourly
    # cadence — no denormalisation yet.
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
    q_count = db.execute(
        select(func.count(Deal.id)).where(
            Deal.carrier_id == user_id,
            Deal.status == DealStatus.closed,
            Deal.created_at >= since,
            handoff_exists,
            receipt_exists,
        )
    ).scalar() or 0

    # D — peak collateral. Phase 5 (T5.x). Zero for now.
    d_peak = 0.0

    verify_level = db.execute(
        select(User.highest_verification_level).where(User.id == user_id)
    ).scalar()

    # T_TRUST.1 — when that level was earned. The newest live badge of exactly
    # that level, because that is the one the level is standing on; an older
    # badge of a lower level says nothing about how fresh *this* claim is.
    verify_at = None
    if verify_level is not None:
        verify_at = db.execute(
            select(func.max(VerificationBadge.verified_at)).where(
                VerificationBadge.subject_id == user_id,
                VerificationBadge.level == verify_level,
                VerificationBadge.revoked_at.is_(None),
            )
        ).scalar()

    return UBAComponents(
        f_count=int(f_count),
        q_count=int(q_count),
        v_sum=float(v_sum),
        d_peak=float(d_peak),
        verify_level=verify_level,
        verify_at=verify_at,
    )


def compute_uba(c: UBAComponents) -> int:
    """Formula per PRD §3.1. Returns int in [0, 1000]."""
    # F is a monthly rate over the 90-day window (3 months).
    f_monthly = c.f_count / 3.0
    f_norm = min(f_monthly / 8.0, 1.0)

    q_norm = min(math.log10(c.q_count + 1) / math.log10(51.0), 1.0)
    v_norm = min(math.log10(c.v_sum + 1.0) / math.log10(50001.0), 1.0)

    d_factor = 1.0 + 0.5 * min(c.d_peak / 5000.0, 1.0)

    # T_TRUST.1 — age decays the *bonus*, not the person. The factor moves back
    # toward 1.00, the value of having no verification at all, so a five-year-old
    # proof makes someone ordinary and never worse than someone who was never
    # verified. Multiplying the factor itself would have done the opposite: a
    # 0.4× on 1.30 lands at 0.52, i.e. an old badge would be a penalty.
    factor = _VERIFY_FACTOR.get(c.verify_level, 1.0)
    if c.verify_level is not None:
        factor = 1.0 + (factor - 1.0) * freshness_factor(c.verify_at)
    v_verify_norm = factor / _VERIFY_FACTOR_MAX

    raw = f_norm * q_norm * v_norm * d_factor * v_verify_norm * 1000.0
    return max(0, min(1000, round(raw)))


def level_of(uba: int) -> str:
    current = LEVELS[0][1]
    for threshold, slug in LEVELS:
        if uba >= threshold:
            current = slug
        else:
            break
    return current


def recompute_and_persist(db: Session, user_id: uuid.UUID) -> int:
    """One-shot recompute for a single user — called by hourly Celery beat and
    on-demand from the read endpoint when the cached value is stale."""
    components = compute_components(db, user_id)
    score = compute_uba(components)
    db.execute(
        User.__table__.update().where(User.id == user_id).values(business_activity_level=float(score))
    )
    db.commit()
    return score
