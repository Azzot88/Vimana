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
    arrival: str | None = Query(default=None, min_length=2, max_length=2),
    departure: str | None = Query(default=None, min_length=2, max_length=2),
):
    """How money can move when it moves outside the platform.

    A plain substitution by country, twice: **arrival first, then departure**.
    Settlement most often happens where the cargo changes hands, at the end of
    the flight; but a carrier who lives at the departure end still needs their
    own systems offered rather than typed out. Global names come after both, and
    anything missing is typed by hand.
    """
    return [
        DirectoryEntry(**e)
        for e in directories.payment_systems(arrival, departure)
    ]
