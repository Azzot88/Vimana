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
    build_platform_deletion_event,
    build_platform_trip_event,
    is_publish_enabled,
    platform_publish_pubkey,
    publish_event,
)
from app.core.publish_filter import should_publish
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

        # T3.12 — a carrier who owns their identity publishes themselves, over
        # NIP-07 (`POST /api/nostr/publish-signed`). The server has no key for
        # them and must not invent one.
        if carrier.key_self_custody:
            return {"skipped": "carrier owns their key — client-signed publish"}

        ok, reason = should_publish(db, trip)
        if not ok:
            logger.info("trip %s not published: %s", trip.id, reason)
            return {"skipped": reason}

        # Signed by the platform, never by the carrier's service key: a service
        # key is destroyed the moment its owner takes their own identity, and an
        # event signed by it would outlive it on relays we do not control,
        # attributed to a pubkey that belongs to nobody.
        event = build_platform_trip_event(trip, carrier, _platform_url())
        if event is None:
            return {"skipped": "PLATFORM_PUBLISH_NSEC not configured"}
        results = asyncio.run(publish_event(event))
        trip.nostr_event_id = event["id"]
        trip.nostr_published_at = datetime.now(tz=timezone.utc)
        trip.nostr_published_by_pubkey = event["pubkey"]
        db.commit()
        return {"event_id": event["id"], "relays": results, "reason": reason}


@celery_app.task(name="app.tasks.nostr_publish.delete_trip_from_nostr")
def delete_trip_from_nostr(trip_id: str) -> dict:
    if not is_publish_enabled():
        return {"skipped": "publish disabled"}
    tid = uuid.UUID(trip_id)
    with SyncSessionLocal() as db:
        trip = db.get(Trip, tid)
        if trip is None or trip.nostr_event_id is None:
            return {"skipped": "no published event"}
        # NIP-09: a retraction is only honoured from the key that published.
        # `nostr_published_by_pubkey` records which that was — the carrier's
        # current key is not a safe guess once they have moved to their own.
        platform_pubkey = platform_publish_pubkey()
        if (
            trip.nostr_published_by_pubkey
            and platform_pubkey
            and trip.nostr_published_by_pubkey != platform_pubkey
        ):
            return {
                "skipped": "listing was published under another key — "
                "its owner must retract it"
            }
        event = build_platform_deletion_event(trip.nostr_event_id)
        if event is None:
            return {"skipped": "PLATFORM_PUBLISH_NSEC not configured"}
        results = asyncio.run(publish_event(event))
        return {"event_id": event["id"], "relays": results}
