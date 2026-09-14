"""T3.12.03 pt.2 — the sender's cargo templates, kept in the cabinet.

A list that belongs to one person, with the same posture as the addresses: a
stranger's template is not found rather than forbidden, so its existence is not
disclosed either. There is no default — the response form offers the list and
the sender picks, and «the one I used last time» is not a rule anybody asked for.

Templates are also born at the response to a trip (`api.deals.match_deal`,
`save_as_template`), in the same transaction as the cargo, so a refused response
leaves no template behind.

Functions (PROJECT §6.2a):
- `list_templates` — `GET /api/me/cargo-templates`. Called by: the response page
  and the cabinet section.
- `create_template` — `POST /api/me/cargo-templates`. Called by: the cabinet.
- `update_template` — `PATCH /api/me/cargo-templates/{template_id}`. Called by:
  the cabinet.
- `delete_template` — `DELETE /api/me/cargo-templates/{template_id}`. Called by:
  the cabinet.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.marketplace import CargoTemplate
from app.models.user import User

router = APIRouter()

#: A name made of spaces is no name: stripped first, then measured.
TemplateName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
]


class CargoTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None
    declared_value: float | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CargoTemplateCreate(BaseModel):
    name: TemplateName
    category: str | None = Field(default=None, max_length=50)
    declared_value: float | None = Field(default=None, ge=0, le=1_000_000_000)
    description: str | None = Field(default=None, max_length=1000)


class CargoTemplateUpdate(BaseModel):
    name: TemplateName | None = None
    category: str | None = Field(default=None, max_length=50)
    declared_value: float | None = Field(default=None, ge=0, le=1_000_000_000)
    description: str | None = Field(default=None, max_length=1000)


def _category(value: str | None) -> str | None:
    """Stored as the response stores it (`match_deal`), so a template filled
    from one and offered to the other names the same category."""
    if value is None:
        return None
    return value.strip().lower() or None


async def _own(db: AsyncSession, template_id: uuid.UUID, user: User) -> CargoTemplate:
    template = await db.get(CargoTemplate, template_id)
    if template is None or template.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.get("/me/cargo-templates", response_model=list[CargoTemplateOut])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(CargoTemplate)
            .where(CargoTemplate.owner_id == current_user.id)
            .order_by(CargoTemplate.name, CargoTemplate.created_at)
        )
    ).scalars().all()
    return rows


@router.post("/me/cargo-templates", response_model=CargoTemplateOut, status_code=201)
async def create_template(
    body: CargoTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = CargoTemplate(
        owner_id=current_user.id,
        name=body.name,
        category=_category(body.category),
        declared_value=body.declared_value,
        description=body.description,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.patch("/me/cargo-templates/{template_id}", response_model=CargoTemplateOut)
async def update_template(
    template_id: uuid.UUID,
    body: CargoTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await _own(db, template_id, current_user)
    data = body.model_dump(exclude_unset=True)
    # The name is the one field a template cannot be without; sending `null`
    # for it is not a way to clear it.
    if "name" in data and data["name"] is None:
        raise HTTPException(status_code=422, detail="A template needs a name")
    if "category" in data:
        data["category"] = _category(data["category"])
    for field, value in data.items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/me/cargo-templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await _own(db, template_id, current_user)
    await db.delete(template)
    await db.commit()
