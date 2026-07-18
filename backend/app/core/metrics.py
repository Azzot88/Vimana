"""T3.5 pt.2 — publish metrics counter (Postgres-backed, no Prometheus yet).

Single-row table `metrics_counters` with atomic UPDATE ... SET ... + 1. Good
enough for hourly ops-visibility; move to Redis+Prometheus when we outgrow it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import PublishMetric


async def bump_publish_metric(db: AsyncSession, *, success: bool) -> None:
    row_result = await db.execute(select(PublishMetric).limit(1))
    row = row_result.scalar_one_or_none()
    if row is None:
        row = PublishMetric(success_count=0, error_count=0)
        db.add(row)
        await db.flush()
    if success:
        row.success_count += 1
    else:
        row.error_count += 1
    row.last_attempt_at = datetime.now(tz=timezone.utc)


async def get_publish_metrics(db: AsyncSession) -> dict:
    row_result = await db.execute(select(PublishMetric).limit(1))
    row = row_result.scalar_one_or_none()
    if row is None:
        return {"success_count": 0, "error_count": 0, "last_attempt_at": None}
    return {
        "success_count": row.success_count,
        "error_count": row.error_count,
        "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
    }
