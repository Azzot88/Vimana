from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import airports as airports_module
from app.core.database import get_db
from app.models.marketplace import TripLeg

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


@router.get("/popular", response_model=list[AirportOut])
async def popular_airports(
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.07 — what the picker offers before anything is typed.

    An empty field with a blinking cursor asks the carrier to recall an IATA
    code; this answers with the codes this platform actually flies. Counted over
    `trip_legs` — both ends of every flight, because a corridor is busy in both
    directions and counting only departures would rank the return leg at zero.

    Open without authentication, like the rest of this router: every one of
    these codes is already on the public board. On an empty database it returns
    nothing, and the picker then falls back to the viewer's own recent picks.

    Called by: `frontend/src/components/AirportSelect`.
    """
    ends = union_all(
        select(TripLeg.origin.label("code")),
        select(TripLeg.destination.label("code")),
    ).subquery()
    rows = (
        await db.execute(
            select(ends.c.code, func.count().label("n"))
            .group_by(ends.c.code)
            # Ask for more than needed: codes that are not in the airport
            # dataset (a hand-typed one, a test fixture) are dropped below, and
            # without the margin a few of those would empty the list.
            .order_by(func.count().desc())
            .limit(limit * 4)
        )
    ).all()

    index = {a.iata: a for a in airports_module.all_airports()}
    out: list[AirportOut] = []
    for code, _ in rows:
        airport = index.get(code)
        if airport is not None:
            out.append(_to_out(airport))
        if len(out) == limit:
            break
    return out


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
