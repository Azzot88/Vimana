import csv
import heapq
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pycountry

DATA_PATH = Path(__file__).parent.parent / "data" / "airports.dat"
CITIES_PATH = Path(__file__).parent.parent / "data" / "cities15000.txt"

# OpenFlights uses some country names that differ from pycountry's canonical names
_COUNTRY_ALIASES: dict[str, str] = {
    "russia": "RU",
    "south korea": "KR",
    "north korea": "KP",
    "vietnam": "VN",
    "iran": "IR",
    "syria": "SY",
    "taiwan": "TW",
    "moldova": "MD",
    "bolivia": "BO",
    "venezuela": "VE",
    "tanzania": "TZ",
    "laos": "LA",
    "brunei": "BN",
    "burma": "MM",
    "myanmar": "MM",
    "east timor": "TL",
    "ivory coast": "CI",
    "cape verde": "CV",
    "congo (kinshasa)": "CD",
    "congo (brazzaville)": "CG",
    "swaziland": "SZ",
    "macau": "MO",
    "hong kong": "HK",
    "palestine": "PS",
    "cocos (keeling) islands": "CC",
    "west bank": "PS",
    "kosovo": "XK",
    "netherlands antilles": "AN",
}


def _build_name_to_iso() -> dict[str, str]:
    result: dict[str, str] = {}
    for c in pycountry.countries:
        result[c.name.lower()] = c.alpha_2
        official = getattr(c, "official_name", None)
        if official:
            result[official.lower()] = c.alpha_2
        common = getattr(c, "common_name", None)
        if common:
            result[common.lower()] = c.alpha_2
    result.update(_COUNTRY_ALIASES)
    return result


_NAME_TO_ISO = _build_name_to_iso()


def _load_cities_index() -> dict[tuple[str, str], dict]:
    """Build (name_variant_lower, iso) → {alt_names, population} index from GeoNames.

    Indexed by *every* alt_name variant so that airports whose city string uses one
    spelling (e.g. OpenFlights "Kiev") match a GeoNames record indexed as "Kyiv".
    """
    idx: dict[tuple[str, str], dict] = {}
    if not CITIES_PATH.exists():
        return idx
    with CITIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 15:
                continue
            name = parts[1]
            ascii_name = parts[2]
            alt_names_raw = parts[3]
            iso = parts[8]
            try:
                population = int(parts[14])
            except ValueError:
                population = 0
            if not iso:
                continue
            alt_names_list = [n for n in alt_names_raw.split(",") if n]
            payload = {
                "alt_names": tuple([name, ascii_name] + alt_names_list),
                "population": population,
            }
            variants: set[str] = {name.lower(), ascii_name.lower()}
            for alt in alt_names_list:
                variants.add(alt.lower())
            for variant in variants:
                key = (variant, iso)
                existing = idx.get(key)
                if existing is None or existing["population"] < population:
                    idx[key] = payload
    return idx


@dataclass(frozen=True, slots=True)
class Airport:
    iata: str
    city: str
    country: str
    country_iso: str
    lat: float
    lon: float
    alt_names: tuple[str, ...]
    population: int
    order: int
    # Lower-cased once at load instead of on every keystroke (T_PERF.1). Search
    # ran `.lower()` over ~7 000 airports plus their alternate names per call,
    # which is tens of thousands of throwaway strings per autocomplete request.
    iata_lower: str
    city_lower: str
    country_lower: str
    alt_names_lower: tuple[str, ...]


def _load() -> list[Airport]:
    # Built here, not at module level (T_PERF.1). The GeoNames index comes from
    # an 8.4 MB file and is only ever read by this loop; as a module global it
    # stayed resident for the life of the process for nothing. On a 2 GB box
    # that has already met the OOM killer, that is free memory back.
    city_index = _load_cities_index()

    airports: list[Airport] = []
    with DATA_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 14:
                continue
            iata = row[4].strip()
            kind = row[12].strip().strip('"')
            if not iata or iata == r"\N" or len(iata) != 3 or kind != "airport":
                continue
            try:
                order = int(row[0])
                lat = float(row[6])
                lon = float(row[7])
            except ValueError:
                continue
            country = row[3]
            iso = _NAME_TO_ISO.get(country.lower(), "")
            city = row[2]
            city_meta = city_index.get((city.lower(), iso)) if iso else None
            alt_names = city_meta["alt_names"] if city_meta else (city,)
            population = city_meta["population"] if city_meta else 0
            airports.append(
                Airport(
                    iata=iata.upper(),
                    city=city,
                    country=country,
                    country_iso=iso,
                    lat=lat,
                    lon=lon,
                    alt_names=alt_names,
                    population=population,
                    order=order,
                    iata_lower=iata.lower(),
                    city_lower=city.lower(),
                    country_lower=country.lower(),
                    alt_names_lower=tuple(n.lower() for n in alt_names),
                )
            )
    return airports


_AIRPORTS: list[Airport] = _load()


def all_airports() -> list[Airport]:
    return _AIRPORTS


def search(query: str, limit: int = 10) -> list[Airport]:
    q = query.strip().lower()
    if not q:
        return []

    exact_iata: list[Airport] = []
    starts_iata: list[Airport] = []
    starts_city: list[Airport] = []
    contains: list[Airport] = []
    alt_match: list[Airport] = []

    for a in _AIRPORTS:
        if a.iata_lower == q:
            exact_iata.append(a)
            continue
        if a.iata_lower.startswith(q):
            starts_iata.append(a)
            continue
        if a.city_lower.startswith(q):
            starts_city.append(a)
            continue
        if q in a.city_lower or q in a.country_lower:
            contains.append(a)
            continue
        for name in a.alt_names_lower:
            if q in name:
                alt_match.append(a)
                break

    for group in (starts_iata, starts_city, contains, alt_match):
        group.sort(key=lambda a: -a.population)

    ranked = exact_iata + starts_iata + starts_city + contains + alt_match
    return ranked[:limit]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _by_iata() -> dict[str, Airport]:
    return {a.iata.upper(): a for a in _AIRPORTS if a.iata}


def route_distance_km(origin: str, destination: str) -> float | None:
    """Great-circle distance between two IATA codes, or None if unknown.

    `Trip.origin` / `.destination` hold IATA codes — `AirportSelect` calls
    `onChange(a.iata)`, so the form can only produce a code from the airport
    index. The API schema is a plain `str` though, so a direct POST can put
    anything there; `None` is the honest answer for those, not an exception.

    Straight-line on purpose. Real tracks add roughly 3–7% for airway routing
    and wind on long flights — and far more on short ones over terrain: Tbilisi
    → Yerevan is 175 km here and ~280 km by road. They also only exist *after*
    the vehicle has moved —
    a trip being published has no track to look up. More to the point, we are
    measuring the **delivery route** (where the parcel goes), not the aircraft's
    mileage: a carrier connecting through two hubs is still one Tbilisi →
    Ulaanbaatar hop for our purposes. Anything shown to a user must therefore
    say "straight line", never "kilometres flown".
    """
    index = _by_iata()
    a = index.get((origin or "").strip().upper())
    b = index.get((destination or "").strip().upper())
    if a is None or b is None:
        return None
    return _haversine_km(a.lat, a.lon, b.lat, b.lon)


def nearest(lat: float, lon: float, limit: int = 5) -> list[Airport]:
    # `nsmallest` keeps a heap of `limit` instead of sorting all ~7 000 entries
    # to hand back five (T_PERF.1).
    return heapq.nsmallest(
        limit, _AIRPORTS, key=lambda a: _haversine_km(lat, lon, a.lat, a.lon)
    )


@lru_cache(maxsize=1)
def list_countries() -> list[dict]:
    # The airport table never changes at runtime, so this aggregate is computed
    # once rather than on every request (T_PERF.1). Callers serialise the result
    # and must not mutate it.
    counts: dict[str, int] = {}
    for a in _AIRPORTS:
        if not a.country_iso:
            continue
        counts[a.country_iso] = counts.get(a.country_iso, 0) + 1
    return sorted(
        [{"iso": iso, "count": c} for iso, c in counts.items()],
        key=lambda x: (-x["count"], x["iso"]),
    )


@lru_cache(maxsize=256)
def list_cities(country_iso: str) -> list[dict]:
    # Same reasoning as `list_countries`; ~200 countries bound the cache.
    iso = country_iso.upper()
    counts: dict[str, int] = {}
    for a in _AIRPORTS:
        if a.country_iso != iso:
            continue
        counts[a.city] = counts.get(a.city, 0) + 1
    return sorted(
        [{"city": city, "count": c} for city, c in counts.items()],
        key=lambda x: (-x["count"], x["city"]),
    )


def airports_in_city(country_iso: str, city: str) -> list[Airport]:
    iso = country_iso.upper()
    city_lower = city.strip().lower()
    result = [
        a for a in _AIRPORTS
        if a.country_iso == iso and a.city_lower == city_lower
    ]
    result.sort(key=lambda a: (a.order, a.iata))
    return result


def search_cities(query: str, limit: int = 8) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return []
    matches: dict[tuple[str, str], dict] = {}
    for a in _AIRPORTS:
        if not a.country_iso:
            continue
        hit = False
        for name in a.alt_names_lower:
            if q in name:
                hit = True
                break
        if not hit and q in a.city_lower:
            hit = True
        if not hit:
            continue
        key = (a.country_iso, a.city)
        entry = matches.get(key)
        if entry is None:
            matches[key] = {"count": 1, "population": a.population}
        else:
            entry["count"] += 1
    return sorted(
        [
            {"iso": iso, "city": city, "count": m["count"], "population": m["population"]}
            for (iso, city), m in matches.items()
        ],
        key=lambda x: (-x["population"], -x["count"], x["city"]),
    )[:limit]
