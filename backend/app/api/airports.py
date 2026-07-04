from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core import airports as airports_module

router = APIRouter()


class AirportOut(BaseModel):
    iata: str
    city: str
    country: str
    lat: float
    lon: float


def _to_out(a: airports_module.Airport) -> AirportOut:
    return AirportOut(iata=a.iata, city=a.city, country=a.country, lat=a.lat, lon=a.lon)


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
