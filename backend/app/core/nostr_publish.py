"""T3.5 — Build and publish trip Nostr events (NIP-99 kind 30402).

Signing rules mirror T2.2 pt.2: canonical NIP-01 event id, Schnorr sig over the
32-byte id. Content = JSON `{origin, destination, depart_at, capacity, ...}`.
Tags follow NIP-99 conventions plus our own topic tags.

Toggling:
- `NOSTR_PUBLISH_ENABLED=false` (default) → publisher is a no-op; endpoints 503.
- `NOSTR_PUBLISH_ENABLED=true`  → publish to whitelist `NOSTR_FRIENDLY_RELAYS`.
- `NOSTR_OWN_RELAY_URL`         → additionally publish to our strfry.

Custodial signing only in pt.1: server decrypts the carrier's nsec via
`NSEC_ENCRYPTION_KEY`. Self-custody carriers get their events skipped with a
log line; pt.2 will refactor to NIP-07-driven client-side signing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.core.keypair import decrypt_nsec, sign_event_id
from app.core.signing import compute_event_id
from app.models.marketplace import Trip
from app.models.user import User

logger = logging.getLogger(__name__)

NOSTR_KIND_TRIP = 30402  # NIP-99 Classified Listing (replaceable per `d` tag)


def is_publish_enabled() -> bool:
    return os.getenv("NOSTR_PUBLISH_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def get_friendly_relays() -> list[str]:
    raw = os.getenv("NOSTR_FRIENDLY_RELAYS", "").strip()
    return [r.strip() for r in raw.split(",") if r.strip()]


def get_own_relay_url() -> str | None:
    url = os.getenv("NOSTR_OWN_RELAY_URL", "").strip()
    return url or None


def _tags(trip: Trip) -> list[list[str]]:
    tags: list[list[str]] = [
        ["d", str(trip.id)],
        ["l", trip.origin],
        ["l", trip.destination],
        ["t", "vimana"],
        ["t", "trip"],
        ["published_at", str(int(datetime.now(tz=timezone.utc).timestamp()))],
        ["expires_at", str(int(trip.depart_at.timestamp()))],
        ["capacity", f"{trip.capacity}kg"],
    ]
    for cat in (trip.allowed_categories or []):
        tags.append(["t", str(cat)])
    return tags


def _content(trip: Trip, platform_url: str) -> str:
    return json.dumps(
        {
            "origin": trip.origin,
            "destination": trip.destination,
            "depart_at": trip.depart_at.isoformat(),
            "capacity": trip.capacity,
            "allowed_categories": trip.allowed_categories or [],
            "carrier_pubkey": None,  # filled per-event below
            "platform_url": platform_url,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_event(trip: Trip, carrier: User, platform_url: str) -> dict[str, Any] | None:
    """Assemble a signed NIP-01 event dict. Returns None if the carrier has no
    server-held keypair (self-custody or missing nsec — pt.2 covers that path)."""
    if not carrier.nostr_pubkey or carrier.nsec_encrypted is None or carrier.nsec_nonce is None:
        return None
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    tags = _tags(trip)
    content = _content(trip, platform_url)
    event_id = compute_event_id(carrier.nostr_pubkey, ts, NOSTR_KIND_TRIP, tags, content)
    nsec_hex = decrypt_nsec(bytes(carrier.nsec_nonce), bytes(carrier.nsec_encrypted))
    sig = sign_event_id(event_id, nsec_hex)
    return {
        "id": event_id,
        "pubkey": carrier.nostr_pubkey,
        "created_at": ts,
        "kind": NOSTR_KIND_TRIP,
        "tags": tags,
        "content": content,
        "sig": sig,
    }


def build_deletion_event(
    trip: Trip, carrier: User, target_event_id: str
) -> dict[str, Any] | None:
    """NIP-09 kind 5 delete request for a previously published trip."""
    if not carrier.nostr_pubkey or carrier.nsec_encrypted is None or carrier.nsec_nonce is None:
        return None
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    tags = [["e", target_event_id], ["k", str(NOSTR_KIND_TRIP)]]
    content = "trip cancelled"
    event_id = compute_event_id(carrier.nostr_pubkey, ts, 5, tags, content)
    nsec_hex = decrypt_nsec(bytes(carrier.nsec_nonce), bytes(carrier.nsec_encrypted))
    sig = sign_event_id(event_id, nsec_hex)
    return {
        "id": event_id,
        "pubkey": carrier.nostr_pubkey,
        "created_at": ts,
        "kind": 5,
        "tags": tags,
        "content": content,
        "sig": sig,
    }


async def _publish_one(url: str, event: dict, timeout_s: float = 5.0) -> bool:
    """One-shot publish over websocket. Returns True on OK response."""
    try:
        import websockets
    except ImportError:
        logger.warning("websockets package not available — skipping Nostr publish")
        return False
    try:
        async with asyncio.timeout(timeout_s):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(["EVENT", event]))
                reply = await ws.recv()
                data = json.loads(reply)
                # OK message per NIP-20: ["OK", event_id, true|false, message]
                if isinstance(data, list) and len(data) >= 3 and data[0] == "OK":
                    return bool(data[2])
                return False
    except Exception as exc:  # network, timeout, JSON — one of many
        logger.info("nostr publish to %s failed: %s", url, exc)
        return False


async def publish_event(event: dict) -> dict[str, bool]:
    """Publish to all configured relays; return per-URL result map."""
    urls = list(get_friendly_relays())
    own = get_own_relay_url()
    if own:
        urls.insert(0, own)
    results: dict[str, bool] = {}
    for url in urls:
        results[url] = await _publish_one(url, event)
    return results
