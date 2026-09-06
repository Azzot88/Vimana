"""T3.11.07 — the two country-scoped reference lists the trip form offers.

Postal services (who can carry a parcel onward inside the destination country
after the flight) and payment systems (how money moves when it moves outside
the platform). Different subjects, identical shape: a global set offered
everywhere plus a per-country set, both read from a JSON file that ships in the
image.

One module for both because the loading, caching and lookup are the same code,
and two copies of it would drift the first time one of them grew a feature. The
data lives in two files because the two subjects change for unrelated reasons
and a reviewer should be able to see one diff without the other.

Read from disk once and cached, exactly like `core.airports`: neither list can
change at runtime, and re-parsing a file per request to get the same answer is
work nobody asked for.

Nothing here reaches the network. A directory that phoned a third party would
make publishing a trip depend on somebody else's uptime, and would put our
carriers' route choices into their logs.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

POSTAL_PATH = Path(__file__).parent.parent / "data" / "postal_services.json"
PAYMENT_PATH = Path(__file__).parent.parent / "data" / "payment_systems.json"


class Entry(TypedDict):
    code: str
    name: str


@lru_cache(maxsize=None)
def _load(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return {
        "global": raw.get("global", []),
        "countries": raw.get("countries", {}),
    }


def _for_country(path: str, country_iso: str | None) -> list[Entry]:
    data = _load(path)
    entries: list[Entry] = []
    seen: set[str] = set()
    # Country-specific first: somebody shipping inside Turkey wants PTT above
    # DHL, and the global names are the ones they would have thought of anyway.
    if country_iso:
        for entry in data["countries"].get(country_iso.upper(), []):
            if entry["code"] not in seen:
                seen.add(entry["code"])
                entries.append(entry)
    for entry in data["global"]:
        if entry["code"] not in seen:
            seen.add(entry["code"])
            entries.append(entry)
    return entries


def postal_services(country_iso: str | None) -> list[Entry]:
    """Who can carry a parcel onward inside `country_iso`.

    The country is the **destination** of the trip: onward shipping happens
    after landing, so a flight into New York offers USPS, not СДЭК.

    Called by: `api.directories.list_postal_services`.
    """
    return _for_country(str(POSTAL_PATH), country_iso)


def payment_systems(country_isos: list[str] | None = None) -> list[Entry]:
    """How money can move outside the platform, for the countries given.

    Takes a list rather than one country because payment is between two people
    who are, by the nature of this product, in different places: the sender is
    at one end of the route and the carrier at the other, and either end's
    systems may be the one they agree on.

    Called by: `api.directories.list_payment_systems`.
    """
    entries: list[Entry] = []
    seen: set[str] = set()
    for iso in country_isos or []:
        for entry in _for_country(str(PAYMENT_PATH), iso):
            if entry["code"] not in seen:
                seen.add(entry["code"])
                entries.append(entry)
    if not entries:
        entries = list(_load(str(PAYMENT_PATH))["global"])
    return entries


def known_postal_codes() -> set[str]:
    """Every postal service code the catalogue knows, for validation.

    Called by: `schemas.marketplace`.
    """
    data = _load(str(POSTAL_PATH))
    codes = {e["code"] for e in data["global"]}
    for entries in data["countries"].values():
        codes.update(e["code"] for e in entries)
    return codes
