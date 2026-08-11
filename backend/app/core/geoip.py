"""T_SEC.6 — roughly where a sign-in came from, resolved on our own machine.

MaxMind's GeoLite2 City database is a file we hold (`GEOIP_DB_PATH`), not a
service we call. The alternative — an HTTP lookup at ipinfo or similar — would
mean the address of every sign-in on the platform travelling to a third party,
which is the opposite of a product that runs its own relay, its own mail and a
local OCR instead of a KYC API. The lookup is the private one or it is nothing.

**Optional by construction.** The database is ~70 MB and needs a MaxMind account
to fetch and refresh, so it is not in the image. Without it `place_for` returns
`None`, the letter simply omits the line, and everything else about the letter
still works. This is the one part of `T_SEC.6` that waits on somebody
downloading a file, and it was built so that nothing else waits with it.

Functions (PROJECT §6.2a):
- `place_for(ip) -> str | None` — "Dubai, United Arab Emirates", or `None` when
  the database is absent or the address is not in it.
  Called by: `tasks/notifications.send_new_device`.
- `_reader()` — opens the database once per process, cached.
  Called by: `place_for`.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _reader():
    path = os.getenv("GEOIP_DB_PATH", "").strip()
    if not path or not os.path.exists(path):
        return None
    try:
        import geoip2.database

        return geoip2.database.Reader(path)
    except Exception:
        logger.exception("could not open GeoIP database at %s", path)
        return None


def place_for(ip: str | None) -> str | None:
    """A coarse, honestly-hedged location. Never raises.

    City resolution is a guess at the best of times and a fiction behind a VPN,
    a corporate egress or carrier-grade NAT. The letter's wording carries that
    hedge — it says where the sign-in appears to come from, and never accuses.
    Here the same caution is mechanical: anything unresolved is `None` rather
    than a half-filled string, because "United Arab Emirates" alone is more use
    to a reader than ", United Arab Emirates".

    **Four tiers, because a bare country name answers almost nothing.** A great
    many real sign-ins have no city — VPNs, corporate egress, carrier-grade NAT,
    data centres, and anycast addresses like `8.8.8.8`. Telling the owner only
    "Russia" leaves them exactly where they started, so each tier falls through
    to the next:

    1. `Minneapolis, United States` — the city, when the database has one.
    2. `England, United Kingdom` — the most specific subdivision.
    3. `Russia (Europe/Moscow)` — the time zone, which in a country nine zones
       wide is the difference between "that is my city" and "that is four
       thousand kilometres away". A recorded fact, not a derived one.
    4. `Russia` — when that is genuinely all there is.

    What is deliberately **not** here: guessing a region from latitude and
    longitude ("northern part of the country"). It would need country geometry
    we do not hold, and inventing geography inside a letter whose entire tone is
    "we are not sure" is the wrong trade.
    """
    reader = _reader()
    if reader is None or not ip:
        return None
    try:
        found = reader.city(ip)
    except Exception:
        # Private ranges, addresses absent from the database, a corrupt file
        # mid-update. None of these are worth failing a letter over.
        return None

    def _name(value) -> str:
        return (value or "").strip()

    city = _name(found.city.name)
    country = _name(found.country.name)
    try:
        region = _name(found.subdivisions.most_specific.name)
    except Exception:
        # `most_specific` answers with an empty subdivision rather than raising
        # for most records, but the shape is the library's promise, not ours.
        region = ""
    zone = _name(getattr(found.location, "time_zone", ""))

    local = city or region
    # A city-state repeats itself — "Singapore, Singapore" reads as a bug in the
    # letter rather than as a place.
    if local and country and local != country:
        return f"{local}, {country}"
    if local:
        return local
    if country and zone:
        return f"{country} ({zone})"
    return country or None
