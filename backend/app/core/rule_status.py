"""T3.11.02 — moving a rule set between statuses, and what publication requires.

Two rules this module exists to hold. **A set cannot become `published` unless
every section in it cites a source**, and **no question may answer from a
section the set does not have** (T3.11.05): the short answer is allowed to be
short only because the section behind it carries the quotation. Both checks live
here, on the transition, and not on the editor form — a rule enforced in the UI
is bypassed by a CLI import, by a fixture, and by the first bulk load of a
corpus, which is exactly how the corpora arrive.

Why it is a hard gate rather than a warning: a published rule is a checkable
statement the platform makes about somebody else's law, and an uncited one is
indistinguishable, to the reader, from a cited one. The failure is silent by
construction — a plausible page with nothing behind it — which is why it is
blocked at write time instead of reported later.

**Publication goes through review.** `draft → published` in one move would make
the two permissions meaningless: `RULES_EDIT` writes and sends onward,
`RULES_PUBLISH` accepts. Collapsing the path leaves the split existing only on
paper.

Functions (PROJECT §6.2a):
- `publication_blockers(db, rule_set)` — every reason this set cannot be
  published, as sentences. Empty list = publishable.
  Called by: `transition`, and `api/rules_admin` to show them before the attempt.
- `transition(db, rule_set, to_status, actor, note)` — validate, supersede the
  previous published version, write the journal row.
  Called by: `api/rules_admin.change_status`.
- `next_version(db, direction, jurisdiction_code, category_key)` — the version
  number a new set gets. Called by: `api/rules_admin.create_set`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rules import (
    RuleQuestion,
    RuleSection,
    RuleSet,
    RuleSource,
    RuleStatus,
    RuleStatusEvent,
)
from app.models.user import User


class RuleStatusError(ValueError):
    """The transition asked for is not available, or its conditions are unmet."""


#: What may follow what. `outdated` is terminal: it is history, and history that
#: can be edited back into force is not history.
ALLOWED: dict[RuleStatus, tuple[RuleStatus, ...]] = {
    RuleStatus.draft: (RuleStatus.review,),
    RuleStatus.review: (RuleStatus.draft, RuleStatus.published),
    # Retiring a rule with nothing to replace it is a real need — a requirement
    # that stops existing is not a new version of itself.
    RuleStatus.published: (RuleStatus.outdated,),
    RuleStatus.outdated: (),
}


async def publication_blockers(db: AsyncSession, rule_set: RuleSet) -> list[str]:
    """Every reason this set may not be published. Empty list means it may."""
    blockers: list[str] = []

    sections = (
        await db.execute(
            select(RuleSection).where(RuleSection.rule_set_id == rule_set.id)
        )
    ).scalars().all()

    if not sections:
        blockers.append("The set has no sections: there is nothing to publish.")
        return blockers

    section_ids = [s.id for s in sections]
    sourced = set(
        (
            await db.execute(
                select(RuleSource.section_id).where(
                    RuleSource.section_id.in_(section_ids),
                    func.length(func.trim(RuleSource.quote)) > 0,
                )
            )
        ).scalars().all()
    )

    for section in sections:
        if section.id not in sourced:
            # Named individually rather than counted: "3 sections lack a source"
            # sends the editor hunting, and the anchor is what they need.
            blockers.append(
                f"Section `{section.anchor}` ({section.locale}) cites no source "
                f"with a quotation."
            )

    # A short answer is allowed to be short only because the section behind it
    # carries the quotation. An answer pointing at nothing is a confident
    # sentence about somebody else's border with no way to check it — the one
    # thing this corpus must not publish. Anchors are compared across locales
    # on purpose: a Russian question may legitimately point at a section that
    # exists so far only in English, and blocking that would push editors to
    # write the answer twice instead of translating the section.
    anchors = {s.anchor for s in sections}
    questions = (
        await db.execute(
            select(RuleQuestion).where(RuleQuestion.rule_set_id == rule_set.id)
        )
    ).scalars().all()
    for question in questions:
        if question.section_anchor not in anchors:
            blockers.append(
                f"Question `{question.anchor}` ({question.locale}) answers from "
                f"section `{question.section_anchor}`, which this set does not have."
            )
    return blockers


async def next_version(
    db: AsyncSession, direction, jurisdiction_code: str, category_key: str
) -> int:
    """One past the highest version for this triple.

    Assigned by the server, never by the client: the version is what the unique
    constraint keys on, and a number chosen in a form is a number two editors
    can choose at once.
    """
    highest = (
        await db.execute(
            select(func.max(RuleSet.version)).where(
                RuleSet.direction == direction,
                RuleSet.jurisdiction_code == jurisdiction_code,
                RuleSet.category_key == category_key,
            )
        )
    ).scalar()
    return (highest or 0) + 1


async def transition(
    db: AsyncSession,
    rule_set: RuleSet,
    to_status: RuleStatus,
    actor: User,
    note: str = "",
) -> RuleStatusEvent:
    """Move a set, with every condition checked and the move written down."""
    current = rule_set.status
    if to_status not in ALLOWED.get(current, ()):
        raise RuleStatusError(
            f"A set in `{current.value}` cannot move to `{to_status.value}`"
        )

    if to_status is RuleStatus.published:
        blockers = await publication_blockers(db, rule_set)
        if blockers:
            raise RuleStatusError(" ".join(blockers))

        # Exactly one published version per triple — the partial unique index
        # enforces it in the database, and this is what keeps the API from
        # meeting that error instead of doing the obvious right thing.
        previous = (
            await db.execute(
                select(RuleSet).where(
                    RuleSet.direction == rule_set.direction,
                    RuleSet.jurisdiction_code == rule_set.jurisdiction_code,
                    RuleSet.category_key == rule_set.category_key,
                    RuleSet.status == RuleStatus.published,
                    RuleSet.id != rule_set.id,
                )
            )
        ).scalars().all()
        for old in previous:
            old.status = RuleStatus.outdated
            db.add(
                RuleStatusEvent(
                    rule_set_id=old.id,
                    from_status=RuleStatus.published,
                    to_status=RuleStatus.outdated,
                    actor_id=actor.id,
                    note=f"Superseded by version {rule_set.version}.",
                )
            )
        if previous:
            # Flushed **before** the new status is set, and that ordering is the
            # whole point: Postgres checks the partial unique index per
            # statement, not at commit, and the unit of work does not promise to
            # emit these UPDATEs in the order they were assigned. Without this,
            # publishing a second version would hit `uq_rule_sets_published`
            # halfway through its own transaction.
            await db.flush()

        # A human is vouching for the text at this moment. `reviewed_at` is the
        # date the reader is shown and the daily watcher compares against, so it
        # is set here rather than when somebody opened the editor.
        #
        # A real datetime, not `func.now()`: the session keeps this instance
        # after commit (`expire_on_commit=False`), and a SQL function assigned
        # to the attribute stays a SQL function in Python — anything reading it
        # back in the same request would get an expression instead of a date.
        rule_set.reviewed_at = datetime.now(timezone.utc)
        rule_set.reviewed_by_id = actor.id
        rule_set.needs_review = False

    event = RuleStatusEvent(
        rule_set_id=rule_set.id,
        from_status=current,
        to_status=to_status,
        actor_id=actor.id,
        note=note,
    )
    db.add(event)
    rule_set.status = to_status
    return event
