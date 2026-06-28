import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
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
    if not current_user.is_carrier:
        raise HTTPException(status_code=403, detail="Carrier account required")

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


@router.get("", response_model=list[TripOut])
async def list_trips(
    origin: str | None = None,
    destination: str | None = None,
    date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Trip).where(Trip.status == TripStatus.open)

    if origin:
        stmt = stmt.where(Trip.origin.ilike(f"%{origin}%"))
    if destination:
        stmt = stmt.where(Trip.destination.ilike(f"%{destination}%"))
    if date:
        stmt = stmt.where(cast(Trip.depart_at, Date) == date)

    result = await db.execute(stmt)
    return result.scalars().all()
