"""T3.5 pt.2 — Nostr publish surface: pre-signed publish + republish + metrics.

Three endpoints:
- `POST /api/nostr/publish-signed` — self-custody carrier submits a fully
  NIP-07-signed kind-30402 event; backend verifies sig, forwards to relays,
  stamps `Trip.nostr_event_id`.
- `POST /api/nostr/republish/{trip_id}` — superuser force-republish for a
  custodial carrier when a relay outage left an event unlanded.
- `GET  /api/nostr/metrics` — counters + last publish latency; readable by
  anyone authenticated (public trust signal, not sensitive).
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.keypair import verify_event_id
from app.core.metrics import bump_publish_metric, get_publish_metrics
from app.core.nostr_publish import (
    NOSTR_KIND_TRIP,
    build_event,
    is_publish_enabled,
    publish_event,
)
from app.core.permissions import Permission, require_perm
from app.core.signing import compute_event_id
from app.models.marketplace import Trip
from app.models.user import User

router = APIRouter()


class SignedTripEvent(BaseModel):
    """NIP-01 event fields from `window.nostr.signEvent()`.

    Frontend builds the exact same tag/content shape as `core.nostr_publish
    .build_event` so backend can recompute the id and reject drift.
    """

    trip_id: uuid.UUID
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: list[list[str]]
    content: str
    sig: str


@router.post("/publish-signed")
async def publish_signed_event(
    body: SignedTripEvent,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not is_publish_enabled():
        raise HTTPException(status_code=503, detail="Nostr publish disabled")

    trip = await db.get(Trip, body.trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.carrier_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only carrier can publish own trip")

    if body.kind != NOSTR_KIND_TRIP:
        raise HTTPException(status_code=422, detail=f"Unexpected kind {body.kind}")
    if body.pubkey != current_user.nostr_pubkey:
        raise HTTPException(
            status_code=422,
            detail="Signer pubkey does not match caller's npub",
        )

    # Recompute id from provided fields — reject drift + verify sig.
    recomputed_id = compute_event_id(
        body.pubkey, body.created_at, body.kind, body.tags, body.content
    )
    if recomputed_id != body.id:
        raise HTTPException(status_code=422, detail="Client-provided id doesn't match recomputed id")
    if not verify_event_id(body.id, body.sig, body.pubkey):
        raise HTTPException(status_code=422, detail="Invalid Schnorr signature")

    event = {
        "id": body.id,
        "pubkey": body.pubkey,
        "created_at": body.created_at,
        "kind": body.kind,
        "tags": body.tags,
        "content": body.content,
        "sig": body.sig,
    }
    results = await publish_event(event)
    ok = any(results.values())
    await bump_publish_metric(db, success=ok)

    trip.nostr_event_id = body.id
    from datetime import datetime, timezone
    trip.nostr_published_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return {"event_id": body.id, "relays": results}


@router.post("/republish/{trip_id}")
async def republish_trip(
    trip_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.NOSTR_REPUBLISH)),
    db: AsyncSession = Depends(get_db),
):
    if not is_publish_enabled():
        raise HTTPException(status_code=503, detail="Nostr publish disabled")
    trip = await db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    carrier = await db.get(User, trip.carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")

    event = build_event(trip, carrier, "https://vimana.dealvault.club")
    if event is None:
        raise HTTPException(
            status_code=422,
            detail="Carrier self-custody — republish only for custodial carriers",
        )

    results = await publish_event(event)
    ok = any(results.values())
    await bump_publish_metric(db, success=ok)

    trip.nostr_event_id = event["id"]
    from datetime import datetime, timezone
    trip.nostr_published_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return {"event_id": event["id"], "relays": results, "forced": True}


@router.get("/metrics")
async def get_metrics(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_publish_metrics(db)
