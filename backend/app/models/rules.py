"""T3.11.01 — corridor rules: what a thing needs in order to cross a border.

Everything built so far answers "what happened between two people". This answers
a different question, and the one that kills a delivery earliest: **will the
object be let through**. MASTERPLAN §4.1 stream D, IMPLEMENTATIONPLAN §6.11.

Four decisions are load-bearing, and each one exists because the obvious
alternative is wrong rather than merely worse.

**A jurisdiction is a tree, and a corridor is a chain.** Not a pair of country
codes. Breed and generation bans on animals live in a state or a city ordinance,
so a rule attached to `US` cannot express them — it can only say "in some states
this is banned", which is not an answer. And there are no direct Russia → US
flights, so a transit country is present in *every* case on the founding
corridor, not in an edge case.

**`RouteNote` (T_UX.2) is not replaced by any of this.** It stays a badge: one
word about a corridor, on a trip card. A badge warns, a rule set explains. Merging
them would turn the badge into an article and the article into a badge.

**One published version per (direction, jurisdiction, category).** Enforced by a
partial unique index, not by application care. Two published sets are two answers
to one question, and a reference book with two answers is not a reference book.

**Three dates, and they are not interchangeable.** `effective_from` is when the
rule started applying, `reviewed_at` is when a human last checked it against the
source, `checked_at` is when the machine last looked at the source page. The
daily watcher (T3.11.11) may move `checked_at` and raise `needs_review`, and may
never touch the text — a scraper rewriting legal prose on a schedule is always
fresh and sometimes wrong, and the reader cannot tell which.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.core.rule_conditions import validate_condition


class JurisdictionKind(str, enum.Enum):
    country = "country"
    subdivision = "subdivision"   # US-NY
    city = "city"                 # US-NY-NYC
    transit_point = "transit_point"  # TR-IST — an airport a corridor passes through


class RuleDirection(str, enum.Enum):
    # `import_` because `import` is a keyword. This is the only enum in the
    # project whose member name differs from its value, and that matters: by
    # default SQLAlchemy persists the *name*, which would put `import_` in the
    # database and in the public URL. Every column below therefore declares
    # `values_callable` — see `_direction_column`.
    export = "export"
    import_ = "import"
    transit = "transit"


def _direction_column() -> SAEnum:
    """Persist `RuleDirection` by value, not by member name.

    The label reaches two places outside Python — the enum type in Postgres and
    the `/rules/<category>/<direction>/<country>/` URL — and `import_` in either
    of them is a leaked keyword workaround.
    """
    return SAEnum(
        RuleDirection,
        name="ruledirection",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class RuleStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    published = "published"
    outdated = "outdated"


class ObtainedBy(str, enum.Enum):
    """Who has to walk out and get the paper.

    Not who benefits from it — who is responsible for producing it. On export
    that is usually the sender; on import it is often the recipient or the
    carrier, and getting this wrong sends the wrong person to the wrong office.
    """

    sender = "sender"
    carrier = "carrier"
    recipient = "recipient"


class Jurisdiction(Base):
    """A node in the chain a corridor passes through.

    `code` is the primary key on purpose: it is stable, human-readable, appears
    in public URLs and in MCP responses, and a surrogate id would mean joining a
    table to answer "which country is this".
    """

    __tablename__ = "jurisdictions"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # RU, US, US-NY
    kind: Mapped[JurisdictionKind] = mapped_column(SAEnum(JurisdictionKind))
    parent_code: Mapped[str | None] = mapped_column(
        ForeignKey("jurisdictions.code"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleSet(Base):
    """One corpus: this direction, this jurisdiction, this cargo category."""

    __tablename__ = "rule_sets"
    __table_args__ = (
        # The invariant of the whole subsystem. Partial index rather than a
        # plain unique constraint because superseded versions must stay in the
        # table — the archive is what makes "what did this say in March"
        # answerable.
        Index(
            "uq_rule_sets_published",
            "direction",
            "jurisdiction_code",
            "category_key",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        UniqueConstraint(
            "direction",
            "jurisdiction_code",
            "category_key",
            "version",
            name="uq_rule_sets_version",
        ),
        # The public page and the MCP tool both read by the triple.
        Index("ix_rule_sets_lookup", "category_key", "direction", "jurisdiction_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    direction: Mapped[RuleDirection] = mapped_column(_direction_column())
    jurisdiction_code: Mapped[str] = mapped_column(ForeignKey("jurisdictions.code"))
    # References the category registry the trips already use (T1.17). A second
    # category system would make a rule impossible to attach to a trip whose
    # category is already chosen.
    category_key: Mapped[str] = mapped_column(
        ForeignKey("categories.name_key"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[RuleStatus] = mapped_column(
        SAEnum(RuleStatus), default=RuleStatus.draft, index=True
    )
    title: Mapped[str] = mapped_column(String(300), default="")

    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # A human read the source and vouched for the text. Null means nobody has.
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # The daily watcher looked at the source. Says nothing about the text being
    # right — only that we are not blind to the source having moved.
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    needs_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleSection(Base):
    """A block of text inside a set, in one locale.

    Per-row locale rather than a JSONB blob of translations: the corpus is
    written in English and Russian first and translated later (T3.11.13), and a
    blob has no state for "sixty per cent translated". A row either exists for a
    locale or it does not, and that is exactly the state the page needs in order
    to fall back honestly instead of showing a hole.
    """

    __tablename__ = "rule_sections"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "anchor", "locale", name="uq_rule_sections_anchor"),
        Index("ix_rule_sections_render", "rule_set_id", "locale", "order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"))
    # Stable slug for deep-linking a single paragraph — from the checklist, from
    # a deal card, from an MCP answer.
    anchor: Mapped[str] = mapped_column(String(64))
    order: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(5), default="en")
    title: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleSource(Base):
    """Where the section's claim comes from. Mandatory before publication.

    `quote` is a verbatim quotation, not a paraphrase. Same reason the NIP-44
    vectors are taken from the spec repository rather than written by hand
    (T_TEST.13): an authority invented on the spot checks the text against
    itself and is worse than no check, because it looks like proof.

    The check that this exists lives on the status transition (T3.11.02), not on
    the editor form. A rule enforced in the UI is bypassed by any script and by
    the first bulk import.
    """

    __tablename__ = "rule_sources"
    __table_args__ = (Index("ix_rule_sources_section", "section_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sections.id"))
    authority: Mapped[str] = mapped_column(String(200))       # CDC, USDA APHIS, Минкультуры
    document_title: Mapped[str] = mapped_column(String(500))
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), default="")
    quote: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentRequirement(Base):
    """One paper, and the condition under which it is needed.

    `lead_time_days` is the field the product is actually built around. Rules a
    person can find without us; the fact that a certificate takes three weeks and
    the flight is in ten days is what they cannot see, and the checklist counts
    it backwards from `Trip.depart_at` (T3.11.06).

    `issuer` is a column and not a phrase inside `notes` because a partner
    executor attaches to it on rung 1 of Platform-not-broker, and parsing prose
    after the fact is exactly the work that column avoids.
    """

    __tablename__ = "document_requirements"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "code", name="uq_document_requirements_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"))
    # Stable across sets so the checklist can merge duplicates arriving from two
    # jurisdictions in the same chain.
    code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    issuer: Mapped[str] = mapped_column(String(200), default="")
    obtained_by: Mapped[ObtainedBy] = mapped_column(
        SAEnum(ObtainedBy), default=ObtainedBy.sender
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # Validated by `core.rule_conditions.validate_condition` before it is stored.
    # Null means unconditional.
    condition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    valid_for_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @validates("condition")
    def _check_condition(self, _key: str, value: dict | None) -> dict | None:
        """Reject an unstorable predicate at the model, not at the endpoint.

        The editor screen (T3.11.02) will validate too, but validation that
        exists only in the API is bypassed by a CLI import, a fixture and a
        migration — and a predicate with a typo'd attribute is invisible
        afterwards: it parses, it stores, and it silently never fires.
        """
        validate_condition(value)
        return value


class RuleStatusEvent(Base):
    """T3.11.02 — who moved a rule set to which status, and when.

    Append-only, same shape and same reason as `RoleGrant` (T3.42): a published
    rule is a **checkable statement the platform makes about somebody else's
    law**, and "who stood behind this" has to be answerable from the table
    rather than from memory. The status column alone says where a set is now
    and is silent about how it got there.

    Not folded into columns on `RuleSet` (`published_at`, `published_by`): a set
    goes `draft → review → published` and can be sent back, so a column pair
    holds only the last move and quietly overwrites the one before it.

    `note` is free text from the editor — why it went to review, why it was sent
    back. Optional here, unlike the reason on a role withdrawal: sending a draft
    onward is not an action taken against anybody.
    """

    __tablename__ = "rule_status_events"
    __table_args__ = (
        Index("ix_rule_status_events_set", "rule_set_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"))
    # Null for the row that records creation: there was no status before it.
    from_status: Mapped[RuleStatus | None] = mapped_column(
        SAEnum(RuleStatus, name="rulestatus"), nullable=True
    )
    to_status: Mapped[RuleStatus] = mapped_column(SAEnum(RuleStatus, name="rulestatus"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleQuestion(Base):
    """A question a reader actually asks, and the short answer, in one locale.

    The corpus is written as law: a section per rule, each carrying the verbatim
    text it rests on. That is the right shape for a document somebody has to be
    able to check, and the wrong shape for a person who wants to know whether
    they can put a painting in a suitcase on Thursday. This table is the second
    reading of the same corpus — the compact one.

    **A question is an index into a sourced section, not a new claim.**
    `section_anchor` must resolve to a section of the same set, and publication
    is blocked when it does not (`core.rule_status.publication_blockers`). That
    constraint is the whole design: the short answer is allowed to be short
    precisely because one click away is the section with the quotation, the
    authority and the date. An answer with nothing behind it would be the one
    thing this corpus must never produce — a confident sentence about somebody
    else's border with no way to check it.

    Locale is per row for the same reason as `RuleSection`: half-translated is a
    real state and the page has to be able to say so.
    """

    __tablename__ = "rule_questions"
    __table_args__ = (
        UniqueConstraint(
            "rule_set_id", "anchor", "locale", name="uq_rule_questions_anchor"
        ),
        Index("ix_rule_questions_render", "rule_set_id", "locale", "order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"))
    # Its own slug, so a single question can be deep-linked and cited — the
    # checklist and the MCP answer both need to point at one.
    anchor: Mapped[str] = mapped_column(String(64))
    order: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(5), default="en")
    question: Mapped[str] = mapped_column(String(500))
    # Markdown, like `RuleSection.body`. Rendered client-side with raw HTML off.
    answer: Mapped[str] = mapped_column(Text, default="")
    # The section this answer compresses. Not nullable: see the class docstring.
    section_anchor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
