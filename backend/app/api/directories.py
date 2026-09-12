"""T3.11.07 — the two reference lists the trip form offers.

Open without authentication, like `api.airports`: these are catalogues of
publicly known company names, they change only when the image is rebuilt, and
requiring a token would mean the picker could not be used on the page where a
carrier is still deciding whether to sign up.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import directories
from app.core.database import get_db
from app.models.marketplace import Trip, TripStatus

router = APIRouter()


class DirectoryEntry(BaseModel):
    code: str
    name: str


@router.get("/postal-services", response_model=list[DirectoryEntry])
async def list_postal_services(
    country: str | None = Query(default=None, min_length=2, max_length=2),
    db: AsyncSession = Depends(get_db),
):
    """Who can carry a parcel onward inside a country after the flight lands.

    The country is the trip's **destination**: onward shipping happens after
    arrival, so a flight into New York offers USPS and one into Istanbul offers
    PTT. Without a country the answer is the global couriers alone, which is the
    honest response to "somewhere, I have not said where yet".

    **Ordered by what carriers on this route actually chose** (owner's «можно»,
    2026-09-06; unblocked 2026-09-09). The file's order is a seed seeded from how
    often the market *names* a service, and a seed only has to answer the cold
    start: once real trips carry real choices, the choices outrank it — the same
    arrangement as `Category.usage_count` beating `sort_order`. Until this the
    order could not move because the picker was not wired to the form and there
    was nothing to count; it is wired now.

    Seeded order survives as the tiebreaker, so a country with no trips yet reads
    exactly as it did. Nothing is hidden and nothing is added: only the order
    changes, because a picker that dropped an unused service would be a picker
    that cannot describe the one pick-up point down somebody's road.
    """
    raw = directories.postal_services(country)
    if country is None or not raw:
        return [DirectoryEntry(**e) for e in raw]

    used = await _postal_usage(db, country)
    # The rule itself lives in `core.directories.order_by_usage`, named and
    # tested on its own: an ordering written inline in a handler is an ordering
    # whose test has to publish trips to observe it, and that test then depends
    # on a database nobody resets.
    return [DirectoryEntry(**e) for e in directories.order_by_usage(raw, used)]


async def _postal_usage(db: AsyncSession, country: str) -> dict[str, int]:
    """How often each service was named on a trip arriving in `country`.

    Counted over `Trip.handover_destination.postal_services` — the arrival end,
    because that is the leg onward shipping belongs to. Names are free text
    (`T3.11.22`: this catalogue has no external source and must not tell a
    carrier their local service does not exist), so they are matched
    case-folded and nothing else: normalising further would merge «CDEK» and
    «СДЭК», which are one company written in two alphabets and two rows to
    anybody trying to correct a typo later.

    Open trips only. A count that included cancelled and flown ones would rank
    the picker by history rather than by what is being chosen now, and the seed
    it replaces was at least about the present.

    Called by: `list_postal_services`.
    """
    from app.core.airports import country_of

    rows = (
        await db.execute(
            select(Trip.destination, Trip.handover_destination).where(
                Trip.status == TripStatus.open,
                Trip.handover_destination.is_not(None),
            )
        )
    ).all()
    counts: dict[str, int] = {}
    wanted = country.upper()
    for destination, side in rows:
        # Filtered in Python rather than in SQL: the trip stores an airport and
        # the caller asks about a country, and the mapping lives in the airport
        # index (`core.airports.country_of`). A SQL filter would need that table
        # in the database — a second copy of what the index already knows, and
        # the copy is the one that goes stale.
        if country_of(destination) != wanted:
            continue
        for name in (side or {}).get("postal_services") or []:
            if isinstance(name, str) and name.strip():
                key = name.strip().casefold()
                counts[key] = counts.get(key, 0) + 1
    return counts




@router.get("/payment-systems", response_model=list[DirectoryEntry])
async def list_payment_systems(
    arrival: str | None = Query(default=None, min_length=2, max_length=2),
    departure: str | None = Query(default=None, min_length=2, max_length=2),
):
    """How money can move when it moves outside the platform.

    A plain substitution by country, twice: **arrival first, then departure**.
    Settlement most often happens where the cargo changes hands, at the end of
    the flight; but a carrier who lives at the departure end still needs their
    own systems offered rather than typed out. Global names come after both, and
    anything missing is typed by hand.
    """
    return [
        DirectoryEntry(**e)
        for e in directories.payment_systems(arrival, departure)
    ]
