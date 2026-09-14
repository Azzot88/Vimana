"""T3.11.15 — the trip chain: ordering, normalisation and the denormalised head.

A trip is an ordered list of flights. This module owns the two operations the
rest of the code needs from that list and nothing else: putting a submitted
chain into canonical form, and deriving the three denormalised columns
(`Trip.origin`, `Trip.destination`, `Trip.depart_at`) that search, the board,
the Nostr event and the T3.11.06 countdown still stand on.

Kept out of the router on purpose: the same normalisation has to apply to a CLI
import and a fixture, and a rule that only the endpoint enforces is a rule that
the next non-HTTP writer skips silently.
"""

from datetime import datetime
from typing import Any

# A chain of more than this is not a trip a person can describe in one listing.
# Real posts top out at six cities; ten leaves room without leaving the door
# open to a payload that turns one listing into a database.
MAX_SEGMENTS = 10


class SegmentChainError(ValueError):
    """A submitted chain that cannot be stored as written."""


def normalise_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical form of a submitted chain, in submission order.

    Airport codes are upper-cased here rather than at each reader: the filter in
    `list_trips` compares exactly, so a segment stored as `dxb` would be invisible
    to every search for `DXB`. It is the write side that has to decide the
    shape.

    `segment_order` is assigned densely from zero and is *not* taken from the
    request. A client-supplied order can arrive sparse, duplicated or
    out of step with the array it came in, and the unique constraint would then
    reject the row for a reason the carrier cannot act on.

    Called by: `api.trips.create_trip`.
    """
    if not segments:
        raise SegmentChainError("a trip needs at least one segment")
    if len(segments) > MAX_SEGMENTS:
        raise SegmentChainError(f"a trip carries at most {MAX_SEGMENTS} segments")

    out: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        origin = str(segment["origin"]).strip().upper()
        destination = str(segment["destination"]).strip().upper()
        if not origin or not destination:
            raise SegmentChainError(f"segment {index + 1}: origin and destination are required")
        if origin == destination:
            raise SegmentChainError(f"segment {index + 1}: origin and destination are the same")
        depart_at = segment["depart_at"]
        if not isinstance(depart_at, datetime):
            raise SegmentChainError(f"segment {index + 1}: departure is not a date")
        # T3.11.07 — arrival is optional and asked only for the end of the route
        # (owner's decision 2026-09-06). `None` is a real answer: 29.8 % of this
        # market states a departure hour at all, and a landing time it does not
        # know is not one it should be made to invent.
        arrive_at = segment.get("arrive_at")
        if arrive_at is not None and not isinstance(arrive_at, datetime):
            raise SegmentChainError(f"segment {index + 1}: arrival is not a date")
        if arrive_at is not None and arrive_at < depart_at:
            raise SegmentChainError(f"segment {index + 1}: arrives before it departs")
        out.append(
            {
                "segment_order": index,
                "origin": origin,
                "destination": destination,
                "depart_at": depart_at,
                "arrive_at": arrive_at,
                "flown_by": segment.get("flown_by") or "self",
            }
        )

    # Segments must not travel backwards in time. Deliberately non-strict: a same
    # timestamp is a carrier who knows the date and not the hour on the second
    # flight, which is ordinary, and rejecting it would push them back into
    # writing the return flight in a free-text field — the exact behaviour this
    # model exists to replace.
    for previous, following in zip(out, out[1:]):
        if following["depart_at"] < previous["depart_at"]:
            raise SegmentChainError(
                f"segment {following['segment_order'] + 1} departs before segment "
                f"{previous['segment_order'] + 1}"
            )
    return out


def head_and_tail(segments: list[dict[str, Any]]) -> tuple[str, str, datetime]:
    """The denormalised `(origin, destination, depart_at)` for a chain.

    Departure is the *first* segment's: it is the moment the cargo has to be in the
    carrier's hands, which is what a countdown and a date filter mean by the
    date of a trip. Destination is the last segment's — where the cargo ends up.

    Called by: `api.trips.create_trip`.
    """
    return segments[0]["origin"], segments[-1]["destination"], segments[0]["depart_at"]


def last_departure(segments: list[dict[str, Any]]) -> datetime:
    """T3.11.16 — when the chain is over, as far as a listing is concerned.

    The **last** segment's departure, deliberately not the first: a trip with a
    transfer is still a live offer on the day its second flight leaves, and
    hiding it when the first one takes off would retire it early — exactly the
    trips a sender with a transfer route is looking for.

    Not the arrival, either: `arrive_at` is optional and most carriers do not
    state it (29.8 % name even the hour of departure), so an expiry built on it
    would be null for most trips and the board would keep flown listings on
    screen. Departure is stated by everyone, because a trip has to have one.

    Called by: `api.trips.create_trip`, `api.trips.update_trip`.
    """
    return segments[-1]["depart_at"]
