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
- `GET /api/deals/{deal_id}/checklist` — the case bound to a deal, with the
  ticks derived from what has actually been filed (`T3.11.09`). Parties only.
- `GET /api/checklist/lead-warning` — «не успеваете» for a screen about a trip
  rather than about documents. Public, speaks airport codes.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
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


class DealChecklistItemOut(ChecklistItemOut):
    """A checklist line as it stands **in this deal**."""

    #: True when some attachment on this deal carries this requirement's code.
    #: Derived, never stored: see `Attachment.requirement_code`.
    attached: bool = False
    #: How many documents were filed against it. More than one is normal — a
    #: certificate plus its translation — and a screen that showed only «done»
    #: would hide the second.
    attachment_count: int = 0


class DealChecklistOut(BaseModel):
    case_id: uuid.UUID | None
    items: list[DealChecklistItemOut]
    unanswered: dict[str, list[str]]
    corridor: list[str]
    #: How many mandatory lines are still open. The number the deal screen shows
    #: and the arbiter reads; it never blocks anything (`D-COMPLIANCE-STANCE`).
    open_mandatory: int


@router.get("/deals/{deal_id}/checklist", response_model=DealChecklistOut)
async def deal_checklist(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.09 — the checklist attached to this deal, with what is closed.

    **The list is the snapshot, the ticks are derived.** `ComplianceCase.checklist`
    is frozen at the moment the person answered the questionnaire; whether a line
    is closed is computed here by looking for an attachment carrying its code.
    Two different kinds of fact, kept in the two places that can be right about
    them: what was asked does not change, what has been filed does.

    **Nothing here blocks.** `D-COMPLIANCE-STANCE`: an open line is visible to
    both sides and to the arbiter, and that is the whole mechanism — «вы знали»
    is proved by the record, not by a refusal.

    Called by: the deal screen and the arbiter's view of it.
    """
    from app.models.deal import Attachment, Deal, DealVaultMessage

    deal = (
        await db.execute(select(Deal).where(Deal.id == deal_id))
    ).scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id not in (deal.sender_id, deal.carrier_id, deal.recipient_id):
        # The arbiter reaches a disputed deal through `api/admin`, which keeps
        # its own grant check and its own audit entry. Widening this endpoint to
        # cover them would be a second, unaudited door to the same content.
        raise HTTPException(status_code=403, detail="Not a party to this deal")

    case = (
        await db.execute(
            select(ComplianceCase)
            .where(ComplianceCase.deal_id == deal_id)
            .order_by(ComplianceCase.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if case is None:
        # Not an error: most deals carry no corridor requirements at all, and a
        # 404 would make «нет чеклиста» look like «что-то сломалось».
        return DealChecklistOut(
            case_id=None, items=[], unanswered={}, corridor=[], open_mandatory=0
        )

    codes = (
        (
            await db.execute(
                select(Attachment.requirement_code)
                .join(DealVaultMessage, Attachment.message_id == DealVaultMessage.id)
                .where(
                    DealVaultMessage.deal_id == deal_id,
                    Attachment.requirement_code.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    filed: dict[str, int] = {}
    for code in codes:
        filed[code] = filed.get(code, 0) + 1

    snapshot = case.checklist or {}
    items = [
        DealChecklistItemOut(
            **item,
            attached=item["code"] in filed,
            attachment_count=filed.get(item["code"], 0),
        )
        for item in snapshot.get("items", [])
    ]
    return DealChecklistOut(
        case_id=case.id,
        items=items,
        unanswered=snapshot.get("unanswered", {}),
        corridor=snapshot.get("corridor", []),
        open_mandatory=sum(1 for i in items if i.is_mandatory and not i.attached),
    )


class LeadWarningOut(BaseModel):
    """T3.11.06 — «не успеваете», for a screen that is about a trip and not
    about documents.

    The wizard is a page somebody goes to. This is the same fact delivered where
    they already are: the trip form, and the board. It carries a count and the
    worst offender rather than the whole list — the screen has one line to spend,
    and «нужен документ, который делается 30 дней» is the sentence that makes
    somebody click through.
    """

    #: How many required documents can no longer be started in time.
    too_late: int
    #: The longest lead time among them, in days — the one that reads worst and
    #: is therefore the one worth naming.
    worst_days: int | None = None
    #: What it is. Named, because «какой-то документ» is a warning nobody acts on.
    worst_title: str | None = None
    #: The jurisdictions consulted, so the warning can say on whose authority.
    corridor: list[str] = Field(default_factory=list)


@router.get("/checklist/lead-warning", response_model=LeadWarningOut)
async def lead_warning(
    origin: str = Query(max_length=8),
    destination: str = Query(max_length=8),
    category: str = Query(max_length=50),
    depart_at: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Is anything on this corridor already impossible to prepare in time?

    **Speaks airport codes**, because that is what a trip is written in, and
    resolves them to jurisdictions here (`core.airports.country_of`). Putting the
    mapping in the caller would make every screen that wants this warning carry
    its own copy of «в какой стране DXB».

    Silent by construction when it has nothing to say: no departure, an unknown
    airport, an uncovered corridor and a corridor with time to spare all return
    `too_late = 0`. A warning surface that guesses is one people learn to ignore,
    and the whole value of this line is that it is rare and right.

    `31 %` of this market publishes inside two days of the flight, so this is not
    an edge case — it is the third of listings for which the answer is «нет».
    """
    if depart_at is None:
        return LeadWarningOut(too_late=0)

    from app.core.airports import country_of

    origin_code = country_of(origin)
    destination_code = country_of(destination)
    if not origin_code or not destination_code:
        return LeadWarningOut(too_late=0)

    result = await build_checklist(
        db,
        origin=origin_code,
        destination=destination_code,
        category=category.strip().lower(),
        # No questionnaire here: this screen is not asking anybody anything.
        # Unanswered conditions therefore include their documents (§3.11.6
        # decides strictly), which is the right bias for a warning — it says
        # «проверьте», not «у вас всё в порядке».
        attrs={},
        depart_at=depart_at,
    )
    late = [i for i in result.items if i.too_late and i.is_mandatory]
    worst = max(late, key=lambda i: i.lead_time_days or 0) if late else None
    return LeadWarningOut(
        too_late=len(late),
        worst_days=worst.lead_time_days if worst else None,
        worst_title=worst.title if worst else None,
        corridor=result.corridor,
    )
