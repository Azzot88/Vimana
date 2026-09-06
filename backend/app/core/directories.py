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


def payment_systems(country_isos: list[str] | None = None) -> list[Entry]:
    """How money can move outside the platform, for the countries given.

    Takes a list rather than one country because payment is between two people
    who are, by the nature of this product, in different places: the sender is
    at one end of the route and the carrier at the other, and either end's
    systems may be the one they agree on.

    **Two layers, ours first.** Our own file is curated for the corridors this
    platform actually flies; the vendored HodlHodl catalogue is broad but has
    holes exactly where we launch — on the day it was fetched it held nothing at
    all for Russia, one entry for the United States, and neither Zelle nor
    Venmo. Merging with ours on top means breadth without letting a bitcoin-P2P
    catalogue decide what a Moscow carrier is offered.

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

    isos = [iso.upper() for iso in (country_isos or [])]
    for iso in isos:
        add(_for_country(str(PAYMENT_PATH), iso))
    if not isos:
        add(list(_load(str(PAYMENT_PATH))["global"]))

    vendor_global, vendor_by_country = _hodlhodl()
    for iso in isos:
        add(vendor_by_country.get(iso, []))
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
