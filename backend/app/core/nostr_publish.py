"""T3.5 — Build and publish trip Nostr events (NIP-99 kind 30402).

Signing rules mirror T2.2 pt.2: canonical NIP-01 event id, Schnorr sig over the
32-byte id. Content = JSON `{origin, destination, depart_at, capacity, ...}`.
Tags follow NIP-99 conventions plus our own topic tags.

Toggling:
- `NOSTR_PUBLISH_ENABLED=false` (default) → publisher is a no-op; endpoints 503.
- `NOSTR_PUBLISH_ENABLED=true`  → publish to whitelist `NOSTR_FRIENDLY_RELAYS`.
- `NOSTR_OWN_RELAY_URL`         → additionally publish to our strfry.

Who signs (T3.12): the **platform**, always, for server-side publishing. A
carrier's service key never signs anything that leaves the platform — it is
destroyed when its owner takes their own identity, and an event signed by it
would survive on relays we do not control, attributed to a pubkey belonging to
nobody. Carriers who own their key publish through
`POST /api/nostr/publish-signed`, signing in their own browser.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.core.keypair import sign_event_id
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


def get_platform_publish_nsec() -> str | None:
    """Key the platform publishes trips under (T3.12).

    Separate from `CHAIN_ANCHOR_NSEC` on purpose, for the same reason T3.6 kept
    the anchor key apart from user keys: "this trip exists" and "this is our
    unaltered chain head" are different claims, and one key making both blurs
    who is attesting to what.
    """
    raw = os.getenv("PLATFORM_PUBLISH_NSEC", "").strip().lower()
    if len(raw) != 64 or not all(c in "0123456789abcdef" for c in raw):
        return None
    return raw


def platform_publish_pubkey() -> str | None:
    nsec = get_platform_publish_nsec()
    if nsec is None:
        return None
    from app.core.keypair import npub_from_nsec

    return npub_from_nsec(nsec)


def _platform_tags(trip: Trip) -> list[list[str]]:
    """Trip tags plus an explicit statement of who published and on whose
    behalf. The carrier is named, never impersonated: the event's `pubkey` is
    the platform's, and nothing claims otherwise."""
    return _tags(trip) + [
        ["published_by", "platform"],
        ["vimana_carrier", str(trip.carrier_id)],
    ]


def _platform_content(trip: Trip, carrier: User, platform_url: str) -> str:
    return json.dumps(
        {
            "origin": trip.origin,
            "destination": trip.destination,
            "depart_at": trip.depart_at.isoformat(),
            "capacity": trip.capacity,
            "allowed_categories": trip.allowed_categories or [],
            # Named, not signed for. `carrier_pubkey` stays null while the
            # carrier has no identity of their own — a service key is not one,
            # and putting it here would publish a key we are about to destroy.
            "carrier_name": carrier.display_name,
            "carrier_pubkey": None,
            "published_by": "platform",
            "platform_url": platform_url,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_platform_trip_event(
    trip: Trip, carrier: User, platform_url: str
) -> dict[str, Any] | None:
    """Trip listing authored by the platform. None if no platform key is set."""
    nsec_hex = get_platform_publish_nsec()
    if nsec_hex is None:
        return None
    from app.core.keypair import npub_from_nsec

    pubkey = npub_from_nsec(nsec_hex)
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    tags = _platform_tags(trip)
    content = _platform_content(trip, carrier, platform_url)
    event_id = compute_event_id(pubkey, ts, NOSTR_KIND_TRIP, tags, content)
    return {
        "id": event_id,
        "pubkey": pubkey,
        "created_at": ts,
        "kind": NOSTR_KIND_TRIP,
        "tags": tags,
        "content": content,
        "sig": sign_event_id(event_id, nsec_hex),
    }


def build_platform_deletion_event(target_event_id: str) -> dict[str, Any] | None:
    """NIP-09 retraction of a platform-published listing.

    Must be signed by the key that published: a deletion from anyone else is
    ignored by relays. That is why `Trip.nostr_published_by_pubkey` exists —
    once a carrier moves to their own key, the carrier's *current* key is no
    longer the one that signed the listing.
    """
    nsec_hex = get_platform_publish_nsec()
    if nsec_hex is None:
        return None
    from app.core.keypair import npub_from_nsec

    pubkey = npub_from_nsec(nsec_hex)
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    tags = [["e", target_event_id], ["k", str(NOSTR_KIND_TRIP)]]
    content = "listing withdrawn"
    event_id = compute_event_id(pubkey, ts, 5, tags, content)
    return {
        "id": event_id,
        "pubkey": pubkey,
        "created_at": ts,
        "kind": 5,
        "tags": tags,
        "content": content,
        "sig": sign_event_id(event_id, nsec_hex),
    }


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


# T3.12 — `build_event` / `build_deletion_event` are gone. They signed with the
# carrier's *service* key, which the platform holds and destroys the moment its
# owner takes their own identity. An event signed by it outlives it on relays we
# do not control, attributed to a pubkey that then belongs to nobody. Server-side
# publishing is platform-signed (above); a carrier who owns their key publishes
# through `POST /api/nostr/publish-signed`, signing in their own browser.


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
    """Publish to all configured relays; return per-URL result map.

    Relays are independent of each other, so they are published to at once
    (T_PERF.1). Sequentially, a set of four with the 5-second timeout each took
    up to twenty seconds for one trip — and a single unreachable relay delayed
    every relay behind it in the list. Now the whole fan-out costs one timeout
    at worst. `_publish_one` never raises, so `gather` needs no exception
    handling of its own; the result stays a per-URL map for the audit trail.
    """
    urls = list(get_friendly_relays())
    own = get_own_relay_url()
    if own:
        urls.insert(0, own)
    if not urls:
        return {}
    outcomes = await asyncio.gather(*(_publish_one(url, event) for url in urls))
    return dict(zip(urls, outcomes))
