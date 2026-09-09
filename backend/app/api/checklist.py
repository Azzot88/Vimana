"""T3.11.06 — the checklist wizard: what to get, and by when.

**No authentication on the build endpoint.** The wizard runs before
registration, for the same reason the directory is open (`MASTERPLAN §4.1`): a
sign-up wall in front of free information is a sign-up form pretending to be a
service. Saving a case is the step that can want an owner, and even that accepts
an anonymous one — a person who wants to come back to their list should not have
to make an account first and re-answer everything after.

**Building and saving are two endpoints, not one.** Answering the questionnaire
is iterative — the first pass leaves attributes unanswered, and the list says
which — so a build that wrote a row every time would fill the table with drafts
of one person's thinking. `POST /checklist` computes and returns; `POST
/checklist/cases` freezes what was computed.

Endpoints:
- `POST /api/checklist` — build. Public.
- `POST /api/checklist/cases` — freeze the snapshot. Public; binds to the
  current account when there is one.
- `GET /api/checklist/cases/{case_id}` — read one back, as it was.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.core.checklist import build_checklist
from app.core.database import get_db
from app.models.rules import ComplianceCase
from app.models.user import User

router = APIRouter()


class ChecklistIn(BaseModel):
    """The questionnaire. Every field but the corridor and the category is
    optional, because the wizard is answerable in passes: what is still missing
    comes back in `unanswered` rather than being demanded up front."""

    origin: str = Field(max_length=16)
    destination: str = Field(max_length=16)
    category: str = Field(max_length=50)
    #: Jurisdictions the route passes through. There is always at least one on
    #: the founding corridor — no direct Russia → US flights exist.
    transit: list[str] = Field(default_factory=list, max_length=8)
    #: Answers to the questionnaire, keyed by the attribute names the corpus
    #: itself declares (`core.rule_conditions.ATTRIBUTES`). Not validated against
    #: that list here: an attribute nobody asks about is harmless, and refusing
    #: it would mean the form breaking every time the corpus grows a clause.
    attrs: dict = Field(default_factory=dict)
    #: The departure the countdown is measured against. Without it the list has
    #: no red lines — which is honest, not degraded: «когда-нибудь» has no
    #: deadline.
    depart_at: date | None = None


class ChecklistItemOut(BaseModel):
    code: str
    title: str
    issuer: str
    obtained_by: str
    is_mandatory: bool
    valid_for_days: int | None
    lead_time_days: int | None
    jurisdiction_code: str
    direction: str
    rule_set_id: str
    start_by: date | None
    too_late: bool
    undecided: bool


class ChecklistOut(BaseModel):
    items: list[ChecklistItemOut]
    unanswered: dict[str, list[str]]
    asks: list[str]
    corridor: list[str]


class CaseIn(ChecklistIn):
    trip_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class CaseOut(BaseModel):
    id: uuid.UUID
    origin: str
    destination: str
    category_key: str
    attrs: dict
    checklist: dict
    depart_at: date | None
    trip_id: uuid.UUID | None
    deal_id: uuid.UUID | None


async def _build(db: AsyncSession, body: ChecklistIn) -> ChecklistOut:
    result = await build_checklist(
        db,
        origin=body.origin.strip().upper(),
        destination=body.destination.strip().upper(),
        category=body.category.strip().lower(),
        attrs=body.attrs,
        transit=[t.strip().upper() for t in body.transit if t.strip()],
        depart_at=body.depart_at,
    )
    return ChecklistOut(
        items=[ChecklistItemOut(**vars(i)) for i in result.items],
        unanswered=result.unanswered,
        asks=result.asks,
        corridor=result.corridor,
    )


@router.post("/checklist", response_model=ChecklistOut)
async def make_checklist(body: ChecklistIn, db: AsyncSession = Depends(get_db)):
    """Assemble the list. Nothing is stored — see the module docstring."""
    return await _build(db, body)


@router.post("/checklist/cases", response_model=CaseOut, status_code=201)
async def save_case(
    body: CaseIn,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Freeze the list as it stands.

    Recomputed here rather than accepted from the client: a snapshot the caller
    supplied is a snapshot the caller can write, and this row is what an arbiter
    reads a year later to see what the person was told.
    """
    computed = await _build(db, body)
    case = ComplianceCase(
        user_id=current_user.id if current_user else None,
        origin=body.origin.strip().upper(),
        destination=body.destination.strip().upper(),
        transit=[t.strip().upper() for t in body.transit if t.strip()] or None,
        category_key=body.category.strip().lower(),
        attrs=body.attrs,
        checklist=computed.model_dump(mode="json"),
        depart_at=body.depart_at,
        trip_id=body.trip_id,
        deal_id=body.deal_id,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return CaseOut(
        id=case.id,
        origin=case.origin,
        destination=case.destination,
        category_key=case.category_key,
        attrs=case.attrs,
        checklist=case.checklist,
        depart_at=case.depart_at,
        trip_id=case.trip_id,
        deal_id=case.deal_id,
    )


@router.get("/checklist/cases/{case_id}", response_model=CaseOut)
async def read_case(case_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """The snapshot, unchanged.

    **Not rebuilt on read.** A rule published since must not rewrite the list
    under somebody who is already standing in a queue with the old one; what a
    changed rule produces is a notice, not a silent edit.

    Readable by anybody holding the id, like the directory itself: the row
    contains a corridor, a category and a list of public documents — nothing
    about a person — and an anonymous wizard has no account to check it against.
    """
    case = (
        await db.execute(select(ComplianceCase).where(ComplianceCase.id == case_id))
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseOut(
        id=case.id,
        origin=case.origin,
        destination=case.destination,
        category_key=case.category_key,
        attrs=case.attrs,
        checklist=case.checklist,
        depart_at=case.depart_at,
        trip_id=case.trip_id,
        deal_id=case.deal_id,
    )
