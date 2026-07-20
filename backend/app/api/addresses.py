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
from app.models.address import ReceivingAddress
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


class AddressCreate(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    country_iso: str = Field(min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=150)
    city_geoname_id: int | None = None
    street: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    is_default: bool = False


class AddressUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    country_iso: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=150)
    city_geoname_id: int | None = None
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
