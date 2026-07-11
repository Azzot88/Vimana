import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.models.marketplace import Trip, TripStatus
from app.models.user import User
from app.schemas.marketplace import TripCreate, TripOut

router = APIRouter()


@router.post("", response_model=TripOut, status_code=201)
async def create_trip(
    body: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.can_carry:
        raise HTTPException(status_code=403, detail="Carrier capability required")

    trip = Trip(
        carrier_id=current_user.id,
        origin=body.origin,
        destination=body.destination,
        depart_at=body.depart_at,
        capacity=body.capacity,
        allowed_categories=body.allowed_categories,
        status=TripStatus.open,
    )
    db.add(trip)
    await db.commit()
    await db.refresh(trip)
    return trip


@router.get("", response_model=Page[TripOut])
async def list_trips(
    origin: str | None = None,
    destination: str | None = None,
    date: date | None = None,
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    stmt = select(Trip).where(Trip.status == TripStatus.open)

    if origin:
        stmt = stmt.where(Trip.origin.ilike(f"%{origin}%"))
    if destination:
        stmt = stmt.where(Trip.destination.ilike(f"%{destination}%"))
    if date:
        stmt = stmt.where(cast(Trip.depart_at, Date) == date)

    items, next_cursor = await paginate_desc(db, stmt, Trip, after, clamp_limit(limit))
    return Page(items=items, next_cursor=next_cursor)
