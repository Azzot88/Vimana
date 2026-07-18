"""T3.1 — hourly UBA recompute Celery task.

Runs over every user that has been active as a carrier in the last 90 days
(same window the formula looks at). Users outside the window keep their cached
value — if they come back in, the next hourly beat picks them up.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SyncSessionLocal
from app.core.uba import WINDOW_DAYS, recompute_and_persist
from app.models.deal import Deal
from app.worker import celery_app


@celery_app.task(name="app.tasks.uba.recompute_all_uba")
def recompute_all_uba() -> dict:
    since = datetime.now(tz=timezone.utc) - timedelta(days=WINDOW_DAYS)
    processed = 0
    with SyncSessionLocal() as db:
        carrier_ids = (
            db.execute(
                select(Deal.carrier_id)
                .where(Deal.created_at >= since)
                .distinct()
            )
            .scalars()
            .all()
        )
        for user_id in carrier_ids:
            recompute_and_persist(db, user_id)
            processed += 1
    return {"processed": processed}
