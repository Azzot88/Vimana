"""T3.5 — Celery tasks for Nostr publishing.

Uses the SYNC session (`SyncSessionLocal`) for DB reads/writes because Celery
worker processes are sync. Async publish is bridged via `asyncio.run`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from app.core.database import SyncSessionLocal
from app.core.nostr_publish import (
    build_deletion_event,
    build_event,
    is_publish_enabled,
    publish_event,
)
from app.models.marketplace import Trip
from app.models.user import User
from app.worker import celery_app

logger = logging.getLogger(__name__)


def _platform_url() -> str:
    return os.getenv("VIMANA_PUBLIC_URL", "https://vimana.dealvault.club")


@celery_app.task(name="app.tasks.nostr_publish.publish_trip_to_nostr")
def publish_trip_to_nostr(trip_id: str) -> dict:
    if not is_publish_enabled():
        return {"skipped": "publish disabled"}
    tid = uuid.UUID(trip_id)
    with SyncSessionLocal() as db:
        trip = db.get(Trip, tid)
        if trip is None:
            return {"error": "trip not found"}
        carrier = db.get(User, trip.carrier_id)
        if carrier is None:
            return {"error": "carrier not found"}
        event = build_event(trip, carrier, _platform_url())
        if event is None:
            return {"skipped": "carrier has no server-held nsec (self-custody)"}
        results = asyncio.run(publish_event(event))
        trip.nostr_event_id = event["id"]
        trip.nostr_published_at = datetime.now(tz=timezone.utc)
        db.commit()
        return {"event_id": event["id"], "relays": results}


@celery_app.task(name="app.tasks.nostr_publish.delete_trip_from_nostr")
def delete_trip_from_nostr(trip_id: str) -> dict:
    if not is_publish_enabled():
        return {"skipped": "publish disabled"}
    tid = uuid.UUID(trip_id)
    with SyncSessionLocal() as db:
        trip = db.get(Trip, tid)
        if trip is None or trip.nostr_event_id is None:
            return {"skipped": "no published event"}
        carrier = db.get(User, trip.carrier_id)
        if carrier is None:
            return {"error": "carrier not found"}
        event = build_deletion_event(trip, carrier, trip.nostr_event_id)
        if event is None:
            return {"skipped": "carrier has no server-held nsec"}
        results = asyncio.run(publish_event(event))
        return {"event_id": event["id"], "relays": results}
