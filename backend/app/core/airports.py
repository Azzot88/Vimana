import csv
import math
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "airports.dat"


@dataclass(frozen=True, slots=True)
class Airport:
    iata: str
    city: str
    country: str
    lat: float
    lon: float


def _load() -> list[Airport]:
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
                lat = float(row[6])
                lon = float(row[7])
            except ValueError:
                continue
            airports.append(
                Airport(
                    iata=iata.upper(),
                    city=row[2],
                    country=row[3],
                    lat=lat,
                    lon=lon,
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

    for a in _AIRPORTS:
        iata_l = a.iata.lower()
        city_l = a.city.lower()
        country_l = a.country.lower()

        if iata_l == q:
            exact_iata.append(a)
        elif iata_l.startswith(q):
            starts_iata.append(a)
        elif city_l.startswith(q):
            starts_city.append(a)
        elif q in city_l or q in country_l:
            contains.append(a)

    ranked = exact_iata + starts_iata + starts_city + contains
    return ranked[:limit]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float, limit: int = 5) -> list[Airport]:
    with_dist = [(a, _haversine_km(lat, lon, a.lat, a.lon)) for a in _AIRPORTS]
    with_dist.sort(key=lambda x: x[1])
    return [a for a, _ in with_dist[:limit]]
