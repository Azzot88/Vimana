"""T3.11.03 — the public rules directory. Free, open, and indexable.

No authentication anywhere in this module, and that is the product decision, not
an oversight: `MASTERPLAN §4.1` makes the directory free for the same reason
matching is free — text is copyable, and text nobody can read without an account
is text nobody reads. What is sold is the collected packet, not the knowledge.

Only `published` sets are served. A draft is somebody's work in progress and an
`outdated` one is what a rule used to say; both would read, to a stranger,
exactly like the current answer.

**Every response carries its own trustworthiness.** `reviewed_at` (a person
checked this against the source), `checked_at` (the daily watcher last looked at
the source) and `needs_review` travel as fields, not as a sentence at the bottom
of the page — a machine reading this cannot parse a sentence, and a person
deserves the date next to the claim rather than in a footer.

Endpoints:
- `GET /api/rules` — index of everything published, for the directory and for
  the prerender step that turns it into files.
- `GET /api/rules/{category}/{direction}/{country}` — one set in full.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    RuleDirection,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
)

router = APIRouter()

#: The corpus is written in these two first; the rest are translated from a
#: settled corpus rather than in parallel with it (IMPLEMENTATIONPLAN §3.11.4).
CORPUS_LOCALES = ("en", "ru")
FALLBACK_LOCALE = "en"


class SourceOut(BaseModel):
    authority: str
    document_title: str
    document_date: date | None
    url: str
    quote: str
    model_config = {"from_attributes": True}


class SectionOut(BaseModel):
    anchor: str
    title: str
    body: str
    #: The locale this section was actually served in. Differs from the one
    #: asked for when the corpus has not been translated yet — the page says so
    #: rather than showing English as if it were the translation.
    locale: str
    sources: list[SourceOut]


class RequirementOut(BaseModel):
    code: str
    title: str
    issuer: str
    obtained_by: str
    is_mandatory: bool
    condition: dict | None
    valid_for_days: int | None
    lead_time_days: int | None
    notes: str
    model_config = {"from_attributes": True}


class RuleIndexOut(BaseModel):
    category_key: str
    direction: RuleDirection
    jurisdiction_code: str
    jurisdiction_name: str
    title: str
    reviewed_at: datetime | None
    #: The address this set is served at. Sent rather than assembled by the
    #: caller: the prerender step writes one file per path, and a path built in
    #: two places is a path that differs in one of them.
    path: str


class RuleSetOut(BaseModel):
    id: uuid.UUID
    category_key: str
    direction: RuleDirection
    jurisdiction_code: str
    jurisdiction_name: str
    title: str
    version: int
    effective_from: datetime
    #: A person checked this text against the source on this date.
    reviewed_at: datetime | None
    #: The watcher last looked at the source on this date. Says nothing about
    #: the text being right — only that we are not blind to the source moving.
    checked_at: datetime | None
    #: Something changed at the source and no one has re-read the rule yet.
    needs_review: bool
    #: True when the reader asked for a locale the corpus does not have yet.
    fallback_locale: bool
    locale: str
    sections: list[SectionOut]
    requirements: list[RequirementOut]


def path_for(category: str, direction: RuleDirection, country: str) -> str:
    """`/rules/<category>/<direction>/<country>/` — category first.

    Owner's decision: people search for "how do I take a painting out of
    Russia", not for "what may leave Russia". The category is the subject of
    the search; the country narrows it.
    """
    return f"/rules/{category}/{direction.value}/{country}/"


@router.get("/rules", response_model=list[RuleIndexOut])
async def index(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(RuleSet, Jurisdiction.name)
            .join(Jurisdiction, Jurisdiction.code == RuleSet.jurisdiction_code)
            .where(RuleSet.status == RuleStatus.published)
            .order_by(RuleSet.category_key, RuleSet.direction)
        )
    ).all()
    return [
        RuleIndexOut(
            category_key=rs.category_key,
            direction=rs.direction,
            jurisdiction_code=rs.jurisdiction_code,
            jurisdiction_name=name or rs.jurisdiction_code,
            title=rs.title,
            reviewed_at=rs.reviewed_at,
            path=path_for(rs.category_key, rs.direction, rs.jurisdiction_code),
        )
        for rs, name in rows
    ]


@router.get("/rules/{category}/{direction}/{country}", response_model=RuleSetOut)
async def read_rule(
    category: str,
    direction: RuleDirection,
    country: str,
    db: AsyncSession = Depends(get_db),
    locale: str = Query(default=FALLBACK_LOCALE, max_length=5),
):
    rule_set = (
        await db.execute(
            select(RuleSet).where(
                RuleSet.category_key == category,
                RuleSet.direction == direction,
                RuleSet.jurisdiction_code == country.upper(),
                RuleSet.status == RuleStatus.published,
            )
        )
    ).scalar_one_or_none()
    if rule_set is None:
        # 404 for "no such corridor" and for "nothing published here" alike.
        # The distinction is real but not the reader's: an unpublished draft
        # must not be discoverable by the shape of the answer.
        raise HTTPException(status_code=404, detail="No published rules for this corridor")

    wanted = (locale or FALLBACK_LOCALE).split("-")[0].lower()
    if wanted not in CORPUS_LOCALES:
        wanted = FALLBACK_LOCALE

    all_sections = (
        await db.execute(
            select(RuleSection)
            .where(RuleSection.rule_set_id == rule_set.id)
            .order_by(RuleSection.order)
        )
    ).scalars().all()

    # By anchor, preferring the asked-for locale and falling back per section:
    # a corpus half-translated is a real state, and the honest answer is the
    # translated sections in the reader's language and the rest in English —
    # each one saying which it is.
    by_anchor: dict[str, RuleSection] = {}
    for section in all_sections:
        current = by_anchor.get(section.anchor)
        if current is None or (section.locale == wanted and current.locale != wanted):
            by_anchor[section.anchor] = section

    chosen = sorted(by_anchor.values(), key=lambda s: s.order)
    source_rows = (
        await db.execute(
            select(RuleSource).where(
                RuleSource.section_id.in_([s.id for s in chosen] or [uuid.uuid4()])
            )
        )
    ).scalars().all()
    sources: dict[uuid.UUID, list[RuleSource]] = {}
    for src in source_rows:
        sources.setdefault(src.section_id, []).append(src)

    requirements = (
        await db.execute(
            select(DocumentRequirement)
            .where(DocumentRequirement.rule_set_id == rule_set.id)
            .order_by(DocumentRequirement.code)
        )
    ).scalars().all()

    name = (
        await db.execute(
            select(Jurisdiction.name).where(Jurisdiction.code == rule_set.jurisdiction_code)
        )
    ).scalar()

    return RuleSetOut(
        id=rule_set.id,
        category_key=rule_set.category_key,
        direction=rule_set.direction,
        jurisdiction_code=rule_set.jurisdiction_code,
        jurisdiction_name=name or rule_set.jurisdiction_code,
        title=rule_set.title,
        version=rule_set.version,
        effective_from=rule_set.effective_from,
        reviewed_at=rule_set.reviewed_at,
        checked_at=rule_set.checked_at,
        needs_review=rule_set.needs_review,
        # True when *anything* the reader sees is not in their language.
        fallback_locale=any(s.locale != wanted for s in chosen),
        locale=wanted,
        sections=[
            SectionOut(
                anchor=s.anchor,
                title=s.title,
                body=s.body,
                locale=s.locale,
                sources=[SourceOut.model_validate(x) for x in sources.get(s.id, [])],
            )
            for s in chosen
        ],
        requirements=[RequirementOut.model_validate(r) for r in requirements],
    )
