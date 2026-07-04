from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core import airports as airports_module

router = APIRouter()


class AirportOut(BaseModel):
    iata: str
    city: str
    country: str
    country_iso: str
    lat: float
    lon: float


class CountryOut(BaseModel):
    iso: str
    count: int


class CityOut(BaseModel):
    city: str
    count: int


class CityMatch(BaseModel):
    iso: str
    city: str
    count: int


class LookupOut(BaseModel):
    cities: list[CityMatch]
    airports: list[AirportOut]


def _to_out(a: airports_module.Airport) -> AirportOut:
    return AirportOut(
        iata=a.iata,
        city=a.city,
        country=a.country,
        country_iso=a.country_iso,
        lat=a.lat,
        lon=a.lon,
    )


@router.get("", response_model=list[AirportOut])
async def search_airports(q: str = Query("", min_length=0, max_length=100)):
    return [_to_out(a) for a in airports_module.search(q, limit=10)]


@router.get("/nearest", response_model=list[AirportOut])
async def nearest_airports(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    limit: int = Query(5, ge=1, le=20),
):
    return [_to_out(a) for a in airports_module.nearest(lat, lon, limit=limit)]


@router.get("/countries", response_model=list[CountryOut])
async def countries():
    return airports_module.list_countries()


@router.get("/lookup", response_model=LookupOut)
async def lookup(q: str = Query("", min_length=0, max_length=100)):
    if not q.strip():
        return LookupOut(cities=[], airports=[])
    return LookupOut(
        cities=[CityMatch(**c) for c in airports_module.search_cities(q, limit=8)],
        airports=[_to_out(a) for a in airports_module.search(q, limit=8)],
    )


@router.get("/cities", response_model=list[CityOut])
async def cities(country: str = Query(..., min_length=2, max_length=2)):
    return airports_module.list_cities(country)


@router.get("/by-city", response_model=list[AirportOut])
async def by_city(
    country: str = Query(..., min_length=2, max_length=2),
    city: str = Query(..., min_length=1, max_length=100),
):
    airports = airports_module.airports_in_city(country, city)
    if not airports:
        raise HTTPException(status_code=404, detail="No airports found for this city")
    return [_to_out(a) for a in airports]
