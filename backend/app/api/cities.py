"""T1.26 — /api/cities endpoint for user's receiving address autocomplete."""
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core import cities as cities_module

router = APIRouter()


class CityOut(BaseModel):
    geoname_id: int
    name: str
    country_iso: str
    population: int


@router.get("", response_model=list[CityOut])
async def search_cities(
    q: str = Query("", max_length=100),
    country: str | None = Query(None, min_length=2, max_length=2),
    limit: int = Query(10, ge=1, le=50),
):
    return [
        CityOut(
            geoname_id=c.geoname_id,
            name=c.name,
            country_iso=c.country_iso,
            population=c.population,
        )
        for c in cities_module.search(q, country=country, limit=limit)
    ]
