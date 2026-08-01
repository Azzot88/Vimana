"""T3.5 pt.2 — publish metrics counter (Postgres-backed, no Prometheus yet).

Single-row table `publish_metrics`, incremented with `UPDATE ... SET c = c + 1`.
Good enough for ops-visibility; move to Redis+Prometheus when we outgrow it.

This docstring used to promise that atomic UPDATE while the code did
read-modify-write through the ORM, and to name a table (`metrics_counters`) that
does not exist. Two publishes finishing together both read `n` and both wrote
`n + 1`, so one of them disappeared. The addition now happens in the database,
where reading and adding are one statement (T_PERF.1).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import PublishMetric


async def bump_publish_metric(db: AsyncSession, *, success: bool) -> None:
    column = "success_count" if success else "error_count"
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        update(PublishMetric).values(
            {column: getattr(PublishMetric, column) + 1, "last_attempt_at": now}
        )
    )
    if result.rowcount:
        return
    # First publish ever — there is no row to add to. Two requests racing here
    # can create two rows, and the reader would then see one of them: an
    # undercount of the first few events, once, on a counter that exists for
    # ops-visibility. Worth saying out loud; not worth a migration.
    db.add(
        PublishMetric(
            success_count=1 if success else 0,
            error_count=0 if success else 1,
            last_attempt_at=now,
        )
    )
    await db.flush()


async def get_publish_metrics(db: AsyncSession) -> dict:
    # Column-level select on purpose: `select(PublishMetric)` can be answered
    # from the identity map, and with `expire_on_commit=False` that map still
    # holds the values from before the UPDATE above — the session never saw the
    # new ones, the database computed them.
    row = (
        await db.execute(
            select(
                PublishMetric.success_count,
                PublishMetric.error_count,
                PublishMetric.last_attempt_at,
            ).limit(1)
        )
    ).first()
    if row is None:
        return {"success_count": 0, "error_count": 0, "last_attempt_at": None}
    return {
        "success_count": row.success_count,
        "error_count": row.error_count,
        "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
    }
