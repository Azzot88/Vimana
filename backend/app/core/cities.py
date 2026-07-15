"""T1.26 — city autocomplete for user's receiving address.

Reuses the existing GeoNames `cities15000.txt` dataset from T1.16. Simple prefix
search over ~34k cities; case-insensitive; multilingual via alt_names.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CITIES_PATH = Path(__file__).parent.parent / "data" / "cities15000.txt"


@dataclass(frozen=True, slots=True)
class City:
    geoname_id: int
    name: str  # canonical name
    country_iso: str
    population: int
    alt_names: tuple[str, ...]  # for search matching


def _load_cities() -> list[City]:
    if not CITIES_PATH.exists():
        return []
    result: list[City] = []
    with CITIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 15:
                continue
            try:
                geoname_id = int(parts[0])
            except ValueError:
                continue
            name = parts[1]
            ascii_name = parts[2]
            alt_raw = parts[3]
            iso = parts[8]
            try:
                population = int(parts[14])
            except ValueError:
                population = 0
            if not iso or not name:
                continue
            alts = tuple(n for n in [ascii_name, *alt_raw.split(",")] if n and n != name)
            result.append(
                City(
                    geoname_id=geoname_id,
                    name=name,
                    country_iso=iso,
                    population=population,
                    alt_names=alts,
                )
            )
    return result


_CITIES: list[City] = _load_cities()


def search(q: str, country: str | None = None, limit: int = 10) -> list[City]:
    """Case-insensitive prefix search over name + alt_names. Sorted by population desc."""
    q_norm = q.strip().lower()
    if not q_norm:
        return []
    country_norm = country.strip().upper() if country else None
    matches: list[City] = []
    for city in _CITIES:
        if country_norm and city.country_iso != country_norm:
            continue
        if _matches(city, q_norm):
            matches.append(city)
    matches.sort(key=lambda c: c.population, reverse=True)
    return matches[:limit]


def _matches(city: City, q_norm: str) -> bool:
    if city.name.lower().startswith(q_norm):
        return True
    return any(alt.lower().startswith(q_norm) for alt in city.alt_names)


def get_by_id(geoname_id: int) -> City | None:
    for city in _CITIES:
        if city.geoname_id == geoname_id:
            return city
    return None
