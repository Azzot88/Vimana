"""T_UX.4 A — CRUD for multiple named receiving addresses per user."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.address import MeetingPlace, ReceivingAddress
from app.models.user import User

router = APIRouter()


class AddressOut(BaseModel):
    id: uuid.UUID
    label: str
    country_iso: str
    city: str | None
    city_geoname_id: int | None
    street: str | None
    postal_code: str | None
    note: str | None
    is_default: bool
    created_at: datetime


# Postgres INTEGER is int32 — without the bound a 2^31 value reaches asyncpg
# and dies as an unhandled DataError/500 (found by schemathesis fuzz).
_GEONAME_ID = Field(default=None, ge=1, le=2_147_483_647)


class AddressCreate(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    country_iso: str = Field(min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=150)
    city_geoname_id: int | None = _GEONAME_ID
    street: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    is_default: bool = False


class AddressUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    country_iso: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=150)
    city_geoname_id: int | None = _GEONAME_ID
    street: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)


def _to_out(a: ReceivingAddress) -> AddressOut:
    return AddressOut(
        id=a.id,
        label=a.label,
        country_iso=a.country_iso,
        city=a.city,
        city_geoname_id=a.city_geoname_id,
        street=a.street,
        postal_code=a.postal_code,
        note=a.note,
        is_default=a.is_default,
        created_at=a.created_at,
    )


@router.get("/me/addresses", response_model=list[AddressOut])
async def list_addresses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(ReceivingAddress)
            .where(ReceivingAddress.user_id == current_user.id)
            .order_by(ReceivingAddress.is_default.desc(), ReceivingAddress.created_at)
        )
    ).scalars().all()
    return [_to_out(a) for a in rows]


@router.post("/me/addresses", response_model=AddressOut, status_code=201)
async def create_address(
    body: AddressCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Count existing FIRST — autoflush after db.add() would include the new
    # row in a later SELECT and defeat the "first-address-auto-default" rule.
    prior_count = (
        await db.execute(
            select(func.count())
            .select_from(ReceivingAddress)
            .where(ReceivingAddress.user_id == current_user.id)
        )
    ).scalar_one()

    is_default = body.is_default or prior_count == 0
    if is_default and prior_count > 0:
        await db.execute(
            update(ReceivingAddress)
            .where(ReceivingAddress.user_id == current_user.id)
            .values(is_default=False)
        )

    addr = ReceivingAddress(
        user_id=current_user.id,
        label=body.label,
        country_iso=body.country_iso.upper(),
        city=body.city,
        city_geoname_id=body.city_geoname_id,
        street=body.street,
        postal_code=body.postal_code,
        note=body.note,
        is_default=is_default,
    )
    db.add(addr)
    await db.commit()
    await db.refresh(addr)
    return _to_out(addr)


@router.patch("/me/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: uuid.UUID,
    body: AddressUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    addr = await db.get(ReceivingAddress, address_id)
    if addr is None or addr.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Address not found")
    data = body.model_dump(exclude_unset=True)
    if "country_iso" in data and data["country_iso"]:
        data["country_iso"] = data["country_iso"].upper()
    for field, value in data.items():
        setattr(addr, field, value)
    await db.commit()
    await db.refresh(addr)
    return _to_out(addr)


@router.post("/me/addresses/{address_id}/default", response_model=AddressOut)
async def make_default(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    addr = await db.get(ReceivingAddress, address_id)
    if addr is None or addr.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Address not found")
    await db.execute(
        update(ReceivingAddress)
        .where(ReceivingAddress.user_id == current_user.id)
        .values(is_default=False)
    )
    addr.is_default = True
    await db.commit()
    await db.refresh(addr)
    return _to_out(addr)


@router.delete("/me/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    addr = await db.get(ReceivingAddress, address_id)
    if addr is None or addr.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Address not found")
    was_default = addr.is_default
    await db.delete(addr)
    await db.flush()
    # If we deleted the default, promote another address so the user always
    # has *something* to share via /share-address without extra clicks.
    if was_default:
        next_addr = (
            await db.execute(
                select(ReceivingAddress)
                .where(ReceivingAddress.user_id == current_user.id)
                .order_by(ReceivingAddress.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if next_addr is not None:
            next_addr.is_default = True
    await db.commit()
    return


# ─────────────────────────────────────────────────────────────
# T3.11.07 — meeting places (owner's decision 2026-09-06)
#
# Lives in this module rather than its own because it is the same shape as the
# addresses above and shares the one rule that is easy to get wrong: several per
# user, at most one default, and deleting the default promotes another. Two
# files would mean two copies of that rule, and the copy that drifts is the one
# nobody is looking at.
#
# What it is *not* is an address. An address is where a parcel is sent and has
# the structure the post office needs; a meeting place is «у метро Фили, у
# выхода №3» — a sentence one person says to another. Same list mechanics,
# different thing.
# ─────────────────────────────────────────────────────────────


class MeetingPlaceOut(BaseModel):
    id: uuid.UUID
    description: str
    is_default: bool
    created_at: datetime


class MeetingPlaceCreate(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    is_default: bool = False


class MeetingPlaceUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=300)


def _place_out(p: MeetingPlace) -> MeetingPlaceOut:
    return MeetingPlaceOut(
        id=p.id,
        description=p.description,
        is_default=p.is_default,
        created_at=p.created_at,
    )


async def _owned_place(
    place_id: uuid.UUID, user: User, db: AsyncSession
) -> MeetingPlace:
    """The row, or a 404 — never somebody else's row.

    404 rather than 403 for a place that exists under another account: telling
    a stranger "this id is real but not yours" answers a question they had no
    business asking.

    Called by: `update_meeting_place`, `make_place_default`, `delete_meeting_place`.
    """
    place = await db.get(MeetingPlace, place_id)
    if place is None or place.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meeting place not found")
    return place


@router.get("/me/meeting-places", response_model=list[MeetingPlaceOut])
async def list_meeting_places(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(MeetingPlace)
            .where(MeetingPlace.user_id == current_user.id)
            .order_by(MeetingPlace.is_default.desc(), MeetingPlace.created_at)
        )
    ).scalars().all()
    return [_place_out(p) for p in rows]


@router.post("/me/meeting-places", response_model=MeetingPlaceOut, status_code=201)
async def create_meeting_place(
    body: MeetingPlaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Counted before the insert, exactly as for addresses: autoflush after
    # `db.add()` would include the new row and defeat "the first one is the
    # default".
    prior_count = (
        await db.execute(
            select(func.count())
            .select_from(MeetingPlace)
            .where(MeetingPlace.user_id == current_user.id)
        )
    ).scalar_one()

    is_default = body.is_default or prior_count == 0
    if is_default and prior_count > 0:
        await db.execute(
            update(MeetingPlace)
            .where(MeetingPlace.user_id == current_user.id)
            .values(is_default=False)
        )

    place = MeetingPlace(
        user_id=current_user.id,
        description=body.description.strip(),
        is_default=is_default,
    )
    db.add(place)
    await db.commit()
    await db.refresh(place)
    return _place_out(place)


@router.patch("/me/meeting-places/{place_id}", response_model=MeetingPlaceOut)
async def update_meeting_place(
    place_id: uuid.UUID,
    body: MeetingPlaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    place = await _owned_place(place_id, current_user, db)
    if body.description is not None:
        place.description = body.description.strip()
    await db.commit()
    await db.refresh(place)
    return _place_out(place)


@router.post("/me/meeting-places/{place_id}/default", response_model=MeetingPlaceOut)
async def make_place_default(
    place_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    place = await _owned_place(place_id, current_user, db)
    await db.execute(
        update(MeetingPlace)
        .where(MeetingPlace.user_id == current_user.id)
        .values(is_default=False)
    )
    place.is_default = True
    await db.commit()
    await db.refresh(place)
    return _place_out(place)


@router.delete("/me/meeting-places/{place_id}", status_code=204)
async def delete_meeting_place(
    place_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    place = await _owned_place(place_id, current_user, db)
    was_default = place.is_default
    await db.delete(place)
    await db.flush()
    # Deleting the default promotes the next one, same as for addresses: a list
    # with entries and no default makes every form that offers one start empty.
    if was_default:
        successor = (
            await db.execute(
                select(MeetingPlace)
                .where(MeetingPlace.user_id == current_user.id)
                .order_by(MeetingPlace.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if successor is not None:
            successor.is_default = True
    await db.commit()
    return
