"""T3.12 pt.3 — which trips are worth putting on Nostr.

Owner's decision (2026-07-26): not all of them. Everything a keyless carrier
publishes goes out under one platform key, and a firehose of near-identical
listings from a single pubkey is what friendly relays throttle first. Publishing
selectively is what makes the platform-key approach acceptable at all.

The rule implemented here is **corridor rarity**: a route we have barely seen is
worth announcing, a route we run daily is not. It is computed from our own
`trips` table, needs no geocoding, and gets stricter on its own as the corridor
fills up.

The other rule the owner named — long hops — is deliberately absent. It needs
the distance between origin and destination, and `Trip.origin` / `.destination`
are free text (`"Tbilisi"`), not structured places. Guessing coordinates from a
free-text name would make publication depend on a fuzzy lookup, which is worse
than not having the rule. Adding it properly means giving trips structured
origin/destination (ISO country + geoname id, as `ReceivingAddress` already
has); that is a schema change and belongs in its own task.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.marketplace import Trip

logger = logging.getLogger(__name__)

MODE_INTERESTING = "interesting"
MODE_ALL = "all"
MODE_NONE = "none"

DEFAULT_RARE_CORRIDOR_MAX = 3


def get_mode() -> str:
    mode = os.getenv("NOSTR_PUBLISH_FILTER", MODE_INTERESTING).strip().lower()
    return mode if mode in {MODE_INTERESTING, MODE_ALL, MODE_NONE} else MODE_INTERESTING


def _rare_corridor_max() -> int:
    raw = os.getenv("NOSTR_PUBLISH_RARE_CORRIDOR_MAX", "").strip()
    try:
        return int(raw) if raw else DEFAULT_RARE_CORRIDOR_MAX
    except ValueError:
        return DEFAULT_RARE_CORRIDOR_MAX


def should_publish(db: Session, trip: Trip) -> tuple[bool, str]:
    """(decision, reason). The reason is logged and returned by the task so a
    trip that never appeared on a relay can be explained without guesswork."""
    mode = get_mode()
    if mode == MODE_NONE:
        return False, "filter mode is 'none'"
    if mode == MODE_ALL:
        return True, "filter mode is 'all'"

    threshold = _rare_corridor_max()
    seen = db.scalar(
        select(func.count())
        .select_from(Trip)
        .where(
            Trip.origin == trip.origin,
            Trip.destination == trip.destination,
            Trip.id != trip.id,
        )
    )
    if seen is None:
        seen = 0
    if seen <= threshold:
        return True, f"rare corridor ({seen} prior trips, threshold {threshold})"
    return False, f"common corridor ({seen} prior trips, threshold {threshold})"
