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
# T3.11.07 — the vendored HodlHodl catalogue (owner's decision 2026-09-06).
# Stored verbatim in their shape; provenance and the legal note live in its
# `_source` block. Refreshed by `app/cli/refresh_payment_systems.py`.
HODLHODL_PATH = (
    Path(__file__).parent.parent / "data" / "payment_systems_hodlhodl.json"
)


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


def _country_slice(path: str, country_iso: str | None) -> list[Entry]:
    """Just the rows filed under one country — no global set.

    Separate from `_for_country` because the payment picker walks two countries
    in order, and folding the global names into each pass would drop them
    between arrival and departure, breaking the very order that answers the
    question.
    """
    if not country_iso:
        return []
    return list(_load(path)["countries"].get(country_iso.upper(), []))


def _for_country(path: str, country_iso: str | None) -> list[Entry]:
    entries: list[Entry] = []
    seen: set[str] = set()
    # Country-specific first: somebody shipping inside Turkey wants PTT above
    # DHL, and the global names are the ones they would have thought of anyway.
    for entry in _country_slice(path, country_iso) + _load(path)["global"]:
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


@lru_cache(maxsize=None)
def _hodlhodl() -> tuple[list[Entry], dict[str, list[Entry]]]:
    """The vendored catalogue, reshaped into (global, by-country) once.

    Their rows carry `country_codes` as a list and a `global` flag; ours are
    keyed by country. Converted here rather than in the file so the file stays
    a byte-for-byte copy and an update stays a reviewable diff.

    Codes are prefixed `hh:` so a vendored row can never collide with one of
    ours, and so a stored value says where it came from.
    """
    with HODLHODL_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    world: list[Entry] = []
    by_country: dict[str, list[Entry]] = {}
    for method in raw.get("payment_methods", []):
        entry: Entry = {"code": f"hh:{method['id']}", "name": method["name"]}
        if method.get("global"):
            world.append(entry)
            continue
        for iso in method.get("country_codes") or []:
            by_country.setdefault(iso.upper(), []).append(entry)
    return world, by_country


def payment_systems(
    arrival_iso: str | None = None, departure_iso: str | None = None
) -> list[Entry]:
    """How money can move outside the platform, for the two ends of a route.

    **Arrival first, then departure** (owner's decision 2026-09-06). Both, and
    in that order, because settlement most often happens where the cargo is
    handed over — at the end of the flight — and because a carrier who lives at
    the departure end still needs their own systems offered rather than typed
    out. Neither end alone is enough: this product exists precisely because the
    two people are in different countries.

    Order is the answer here, not just the contents. A picker that mixed the two
    countries alphabetically would bury the systems of the place the parcel is
    actually going.

    **Two layers within each country, ours first.** Our own file is curated for
    the corridors this platform actually flies; the vendored HodlHodl catalogue
    is broad but has holes exactly where we launch — on the day it was fetched
    it held nothing at all for Russia, one entry for the United States, and
    neither Zelle nor Venmo. Merging with ours on top means breadth without
    letting a bitcoin-P2P catalogue decide what a Minsk carrier is offered.

    Called by: `api.directories.list_payment_systems`.
    """
    entries: list[Entry] = []
    seen_codes: set[str] = set()
    # Names are compared case-insensitively across layers: the same service
    # listed by both should appear once, and ours is the one that stays.
    seen_names: set[str] = set()

    def add(candidates: list[Entry]) -> None:
        for entry in candidates:
            name_key = entry["name"].strip().casefold()
            if entry["code"] in seen_codes or name_key in seen_names:
                continue
            seen_codes.add(entry["code"])
            seen_names.add(name_key)
            entries.append(entry)

    vendor_global, vendor_by_country = _hodlhodl()
    # Deduplicated across the two ends as well: a service both countries list —
    # SEPA for two EU ends, Wise almost anywhere — appears once, under the
    # arrival country, which is where it was offered first.
    for iso in (arrival_iso, departure_iso):
        if not iso:
            continue
        code = iso.upper()
        # Ours before theirs within each country, and the global names held back
        # until both countries have had their turn.
        add(_country_slice(str(PAYMENT_PATH), code))
        add(vendor_by_country.get(code, []))

    add(list(_load(str(PAYMENT_PATH))["global"]))
    add(vendor_global)
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
