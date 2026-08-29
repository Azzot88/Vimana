"""T3.11.02 — the rules editor: sets, sections, sources, requirements.

A page in the existing admin area, by the pattern of the ones already there
(`AdminNoticesPage`, `AdminParamsPage`) — not a second panel.

Two permissions, deliberately separate. `RULES_EDIT` writes and sends a draft to
review; `RULES_PUBLISH` accepts it. Publishing is what turns a draft into a
statement the platform makes about somebody else's law, and the person writing
it is not automatically the person who should stand behind it.

**Everything published is frozen.** A `published` or `outdated` set cannot be
edited at all: its sections, sources and requirements are what a reader saw, and
a corrected rule is a **new version**, not a rewritten old one. That is the same
reason a deal's terms are superseded rather than amended in place — and here it
also keeps the checklist snapshot (T3.11.06) meaningful, because the set it was
built from stays what it was.

Endpoints:
- `GET/POST      /api/admin/rules`                       — list / create a draft
- `GET           /api/admin/rules/{set_id}`              — one set, in full
- `PATCH/DELETE  /api/admin/rules/{set_id}`              — edit / drop a draft
- `POST          /api/admin/rules/{set_id}/status`       — draft→review→published
- `POST          /api/admin/rules/{set_id}/sections`
- `PATCH/DELETE  /api/admin/rules/sections/{section_id}`
- `POST          /api/admin/rules/sections/{section_id}/sources`
- `DELETE        /api/admin/rules/sources/{source_id}`
- `POST          /api/admin/rules/{set_id}/requirements`
- `PATCH/DELETE  /api/admin/rules/requirements/{req_id}`
- `GET/POST      /api/admin/jurisdictions`
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import Permission, require_perm
from app.core.rule_conditions import ConditionError, validate_condition
from app.core.rule_status import (
    RuleStatusError,
    next_version,
    publication_blockers,
    transition,
)
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    JurisdictionKind,
    ObtainedBy,
    RuleDirection,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
    RuleStatusEvent,
)
from app.models.user import User

router = APIRouter()

_EDITABLE = (RuleStatus.draft, RuleStatus.review)


# ─────────────────────────────── schemas ───────────────────────────────

class SourceIn(BaseModel):
    authority: str = Field(min_length=1, max_length=200)
    document_title: str = Field(min_length=1, max_length=500)
    document_date: date | None = None
    url: str = Field(default="", max_length=1000)
    # Verbatim, and required. A paraphrase checks the text against whoever
    # wrote it; that is worse than no check, because it looks like proof.
    quote: str = Field(min_length=1)


class SourceOut(SourceIn):
    id: uuid.UUID
    model_config = {"from_attributes": True}


class SectionIn(BaseModel):
    anchor: str = Field(min_length=1, max_length=64)
    locale: str = Field(default="en", min_length=2, max_length=5)
    order: int = 0
    title: str = Field(default="", max_length=300)
    body: str = ""


class SectionOut(SectionIn):
    id: uuid.UUID
    sources: list[SourceOut] = []


class RequirementIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    issuer: str = Field(default="", max_length=200)
    obtained_by: ObtainedBy = ObtainedBy.sender
    is_mandatory: bool = True
    condition: dict | None = None
    valid_for_days: int | None = None
    lead_time_days: int | None = None
    cost_estimate: float | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: str = ""


class RequirementOut(RequirementIn):
    id: uuid.UUID
    model_config = {"from_attributes": True}


class SetIn(BaseModel):
    direction: RuleDirection
    jurisdiction_code: str = Field(min_length=1, max_length=16)
    category_key: str = Field(min_length=1, max_length=50)
    title: str = Field(default="", max_length=300)


class SetPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)


class SetOut(BaseModel):
    id: uuid.UUID
    direction: RuleDirection
    jurisdiction_code: str
    category_key: str
    version: int
    status: RuleStatus
    title: str
    effective_from: datetime
    reviewed_at: datetime | None
    checked_at: datetime | None
    needs_review: bool
    model_config = {"from_attributes": True}


class SetDetailOut(SetOut):
    sections: list[SectionOut] = []
    requirements: list[RequirementOut] = []
    #: Empty when the set may be published. Shown before the button is pressed,
    #: so the editor is not told what is wrong only by being refused.
    blockers: list[str] = []


class StatusIn(BaseModel):
    to: RuleStatus
    note: str = Field(default="", max_length=2000)


class StatusEventOut(BaseModel):
    id: uuid.UUID
    from_status: RuleStatus | None
    to_status: RuleStatus
    actor_id: uuid.UUID | None
    note: str
    created_at: datetime
    model_config = {"from_attributes": True}


class JurisdictionIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    kind: JurisdictionKind
    parent_code: str | None = None
    name: str = Field(default="", max_length=200)


class JurisdictionOut(JurisdictionIn):
    model_config = {"from_attributes": True}


# ─────────────────────────────── helpers ───────────────────────────────

async def _get_set(db: AsyncSession, set_id: uuid.UUID) -> RuleSet:
    rule_set = await db.get(RuleSet, set_id)
    if rule_set is None:
        raise HTTPException(status_code=404, detail="Rule set not found")
    return rule_set


async def _get_editable_set(db: AsyncSession, set_id: uuid.UUID) -> RuleSet:
    """The set, refused if it is frozen.

    One helper rather than the same two lines in eight endpoints: the freeze is
    the invariant, and an invariant re-typed per call site is one somebody
    forgets on the ninth.
    """
    rule_set = await _get_set(db, set_id)
    if rule_set.status not in _EDITABLE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A `{rule_set.status.value}` set is frozen. Publish a new "
                f"version instead of rewriting what people already read."
            ),
        )
    return rule_set


async def _section_and_set(
    db: AsyncSession, section_id: uuid.UUID
) -> tuple[RuleSection, RuleSet]:
    section = await db.get(RuleSection, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section, await _get_editable_set(db, section.rule_set_id)


# ──────────────────────────────── sets ─────────────────────────────────

@router.get("/admin/rules", response_model=list[SetOut])
async def list_sets(
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
    status: RuleStatus | None = None,
    category_key: str | None = None,
):
    stmt = select(RuleSet).order_by(RuleSet.category_key, RuleSet.jurisdiction_code)
    if status:
        stmt = stmt.where(RuleSet.status == status)
    if category_key:
        stmt = stmt.where(RuleSet.category_key == category_key)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/admin/rules", response_model=SetOut, status_code=201)
async def create_set(
    body: SetIn,
    actor: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    if await db.get(Jurisdiction, body.jurisdiction_code) is None:
        raise HTTPException(
            status_code=400, detail=f"Unknown jurisdiction `{body.jurisdiction_code}`"
        )

    rule_set = RuleSet(
        direction=body.direction,
        jurisdiction_code=body.jurisdiction_code,
        category_key=body.category_key,
        title=body.title,
        status=RuleStatus.draft,
        version=await next_version(
            db, body.direction, body.jurisdiction_code, body.category_key
        ),
    )
    db.add(rule_set)
    await db.flush()
    # The journal starts at creation, with no `from_status`: there was none.
    db.add(
        RuleStatusEvent(
            rule_set_id=rule_set.id, to_status=RuleStatus.draft, actor_id=actor.id
        )
    )
    await db.commit()
    await db.refresh(rule_set)
    return rule_set


@router.get("/admin/rules/{set_id}", response_model=SetDetailOut)
async def get_set(
    set_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    rule_set = await _get_set(db, set_id)

    sections = (
        await db.execute(
            select(RuleSection)
            .where(RuleSection.rule_set_id == set_id)
            .order_by(RuleSection.locale, RuleSection.order)
        )
    ).scalars().all()
    sources = (
        await db.execute(
            select(RuleSource).where(
                RuleSource.section_id.in_([s.id for s in sections] or [uuid.uuid4()])
            )
        )
    ).scalars().all()
    by_section: dict[uuid.UUID, list[RuleSource]] = {}
    for src in sources:
        by_section.setdefault(src.section_id, []).append(src)

    requirements = (
        await db.execute(
            select(DocumentRequirement)
            .where(DocumentRequirement.rule_set_id == set_id)
            .order_by(DocumentRequirement.code)
        )
    ).scalars().all()

    return SetDetailOut(
        **SetOut.model_validate(rule_set).model_dump(),
        sections=[
            SectionOut(
                id=s.id,
                anchor=s.anchor,
                locale=s.locale,
                order=s.order,
                title=s.title,
                body=s.body,
                sources=[SourceOut.model_validate(x) for x in by_section.get(s.id, [])],
            )
            for s in sections
        ],
        requirements=[RequirementOut.model_validate(r) for r in requirements],
        blockers=await publication_blockers(db, rule_set),
    )


@router.patch("/admin/rules/{set_id}", response_model=SetOut)
async def patch_set(
    set_id: uuid.UUID,
    body: SetPatch,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    rule_set = await _get_editable_set(db, set_id)
    if body.title is not None:
        rule_set.title = body.title
    await db.commit()
    await db.refresh(rule_set)
    return rule_set


@router.delete("/admin/rules/{set_id}", status_code=204)
async def delete_set(
    set_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    """Only a draft, and only one nobody has sent onward.

    A set that reached review has been looked at by somebody else; deleting it
    would remove the thing they were asked about. Sending it back to draft is
    the move that exists for that.
    """
    rule_set = await _get_set(db, set_id)
    if rule_set.status is not RuleStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=f"Only a draft can be deleted; this one is `{rule_set.status.value}`",
        )

    sections = (
        await db.execute(select(RuleSection).where(RuleSection.rule_set_id == set_id))
    ).scalars().all()
    from sqlalchemy import delete as sa_delete

    if sections:
        await db.execute(
            sa_delete(RuleSource).where(
                RuleSource.section_id.in_([s.id for s in sections])
            )
        )
    await db.execute(sa_delete(RuleSection).where(RuleSection.rule_set_id == set_id))
    await db.execute(
        sa_delete(DocumentRequirement).where(DocumentRequirement.rule_set_id == set_id)
    )
    await db.execute(
        sa_delete(RuleStatusEvent).where(RuleStatusEvent.rule_set_id == set_id)
    )
    await db.delete(rule_set)
    await db.commit()


@router.post("/admin/rules/{set_id}/status", response_model=StatusEventOut)
async def change_status(
    set_id: uuid.UUID,
    body: StatusIn,
    actor: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    """`draft → review → published`, and `published → outdated`.

    Publishing needs `RULES_PUBLISH` on top of `RULES_EDIT`, checked here rather
    than by a second dependency: the route is one, and splitting it into two
    endpoints so the dependency could differ would put the same transition in
    two places.
    """
    from app.core.permissions import has_perm

    rule_set = await _get_set(db, set_id)

    if body.to is RuleStatus.published and not has_perm(actor, Permission.RULES_PUBLISH):
        raise HTTPException(
            status_code=403,
            detail="Publishing a rule needs `rules:publish`; sending it to review does not.",
        )

    try:
        event = await transition(db, rule_set, body.to, actor, body.note)
    except RuleStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(event)
    return event


@router.get("/admin/rules/{set_id}/history", response_model=list[StatusEventOut])
async def status_history(
    set_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import desc

    return list(
        (
            await db.execute(
                select(RuleStatusEvent)
                .where(RuleStatusEvent.rule_set_id == set_id)
                .order_by(desc(RuleStatusEvent.created_at))
            )
        ).scalars().all()
    )


# ────────────────────────────── sections ───────────────────────────────

@router.post("/admin/rules/{set_id}/sections", response_model=SectionOut, status_code=201)
async def add_section(
    set_id: uuid.UUID,
    body: SectionIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    await _get_editable_set(db, set_id)
    section = RuleSection(rule_set_id=set_id, **body.model_dump())
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return SectionOut(**body.model_dump(), id=section.id, sources=[])


@router.patch("/admin/rules/sections/{section_id}", response_model=SectionOut)
async def patch_section(
    section_id: uuid.UUID,
    body: SectionIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    section, _set = await _section_and_set(db, section_id)
    for field, value in body.model_dump().items():
        setattr(section, field, value)
    await db.commit()
    await db.refresh(section)
    return SectionOut(**body.model_dump(), id=section.id, sources=[])


@router.delete("/admin/rules/sections/{section_id}", status_code=204)
async def delete_section(
    section_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete as sa_delete

    section, _set = await _section_and_set(db, section_id)
    await db.execute(sa_delete(RuleSource).where(RuleSource.section_id == section.id))
    await db.delete(section)
    await db.commit()


# ─────────────────────────────── sources ───────────────────────────────

@router.post(
    "/admin/rules/sections/{section_id}/sources",
    response_model=SourceOut,
    status_code=201,
)
async def add_source(
    section_id: uuid.UUID,
    body: SourceIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    section, _set = await _section_and_set(db, section_id)
    source = RuleSource(section_id=section.id, **body.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.patch("/admin/rules/sources/{source_id}", response_model=SourceOut)
async def patch_source(
    source_id: uuid.UUID,
    body: SourceIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    """A citation is the thing most likely to need correcting.

    Delete-and-recreate was the only way to fix a typo in an authority's name,
    and it loses the source's identity for no reason. Sections and requirements
    already had `PATCH`; this was the gap.
    """
    source = await db.get(RuleSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    section, _set = await _section_and_set(db, source.section_id)

    for field, value in body.model_dump().items():
        setattr(source, field, value)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/admin/rules/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(RuleSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    section, _set = await _section_and_set(db, source.section_id)
    await db.delete(source)
    await db.commit()


# ──────────────────────────── requirements ─────────────────────────────

@router.post(
    "/admin/rules/{set_id}/requirements", response_model=RequirementOut, status_code=201
)
async def add_requirement(
    set_id: uuid.UUID,
    body: RequirementIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    await _get_editable_set(db, set_id)
    try:
        validate_condition(body.condition)
    except ConditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    requirement = DocumentRequirement(rule_set_id=set_id, **body.model_dump())
    db.add(requirement)
    await db.commit()
    await db.refresh(requirement)
    return requirement


@router.patch(
    "/admin/rules/requirements/{req_id}", response_model=RequirementOut
)
async def patch_requirement(
    req_id: uuid.UUID,
    body: RequirementIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    requirement = await db.get(DocumentRequirement, req_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await _get_editable_set(db, requirement.rule_set_id)
    try:
        validate_condition(body.condition)
    except ConditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for field, value in body.model_dump().items():
        setattr(requirement, field, value)
    await db.commit()
    await db.refresh(requirement)
    return requirement


@router.delete("/admin/rules/requirements/{req_id}", status_code=204)
async def delete_requirement(
    req_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    requirement = await db.get(DocumentRequirement, req_id)
    if requirement is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await _get_editable_set(db, requirement.rule_set_id)
    await db.delete(requirement)
    await db.commit()


# ───────────────────────────── jurisdictions ───────────────────────────

@router.get("/admin/jurisdictions", response_model=list[JurisdictionOut])
async def list_jurisdictions(
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    return list(
        (await db.execute(select(Jurisdiction).order_by(Jurisdiction.code)))
        .scalars()
        .all()
    )


@router.post("/admin/jurisdictions", response_model=JurisdictionOut, status_code=201)
async def create_jurisdiction(
    body: JurisdictionIn,
    _: User = Depends(require_perm(Permission.RULES_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    """Adding `US-NY` or `US-NY-NYC` as the corpus needs them.

    Seeded with four codes only (0054) — the country pair and two transit
    points. States and cities arrive with the rule that needs them, because a
    list of every subdivision on earth is a list nobody maintains.
    """
    if await db.get(Jurisdiction, body.code) is not None:
        raise HTTPException(status_code=409, detail="This code already exists")
    if body.parent_code and await db.get(Jurisdiction, body.parent_code) is None:
        raise HTTPException(status_code=400, detail="Unknown parent code")

    node = Jurisdiction(**body.model_dump())
    db.add(node)
    await db.commit()
    return node
