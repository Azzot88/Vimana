"""T3.11.07 — the two reference lists the trip form offers.

Open without authentication, like `api.airports`: these are catalogues of
publicly known company names, they change only when the image is rebuilt, and
requiring a token would mean the picker could not be used on the page where a
carrier is still deciding whether to sign up.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core import directories

router = APIRouter()


class DirectoryEntry(BaseModel):
    code: str
    name: str


@router.get("/postal-services", response_model=list[DirectoryEntry])
async def list_postal_services(
    country: str | None = Query(default=None, min_length=2, max_length=2),
):
    """Who can carry a parcel onward inside a country after the flight lands.

    The country is the trip's **destination**: onward shipping happens after
    arrival, so a flight into New York offers USPS and one into Istanbul offers
    PTT. Without a country the answer is the global couriers alone, which is the
    honest response to "somewhere, I have not said where yet".
    """
    return [DirectoryEntry(**e) for e in directories.postal_services(country)]


@router.get("/payment-systems", response_model=list[DirectoryEntry])
async def list_payment_systems(
    countries: str | None = Query(
        default=None,
        max_length=64,
        description="Comma-separated ISO-2 codes, usually both ends of the route.",
    ),
):
    """How money can move when it moves outside the platform.

    Takes several countries because payment is between two people who are, by
    the nature of this product, in different places: the sender is at one end of
    the route and the carrier at the other, and either end's systems may be the
    one they settle in.
    """
    parsed = [c.strip() for c in (countries or "").split(",") if c.strip()]
    return [DirectoryEntry(**e) for e in directories.payment_systems(parsed)]
