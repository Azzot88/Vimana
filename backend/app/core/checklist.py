"""T3.11.06 — turning a corpus of rules into one person's list of documents.

Everything under `T3.11.01`–`T3.11.05` answers «what does the law say». This
answers the only question a sender actually asks: **what do I have to get, and
have I already run out of time.** Until this module existed the corpus had two
readers — the public directory and the editor — and neither of them was a deal.

Three decisions carry the weight here.

**A corridor is a chain of jurisdictions, so the walk is up the tree.** A parcel
leaving Moscow for New York is subject to `RU` on the way out, to whatever
transit country the flight touches, and to `US` **plus the state** on the way in.
Breed and generation bans live below the country level (`T3.11.01`), so a
lookup that stopped at `US` would return an answer that is true and useless.
`chain_for` walks `parent_code` upward and keeps the order, because the order is
what the reader sees.

**Conflicts resolve to the stricter side.** The same document code can appear in
a federal set and a state one with different `is_mandatory` or different
`lead_time_days`. Merging to «optional» or to the shorter lead time would produce
a list that is wrong exactly when it matters — the traveller who follows it
arrives without the paper the stricter jurisdiction wanted. So: mandatory wins
over optional, and the longest lead time wins.

**A missing answer decides strictly, and says so.** `evaluate` raises when the
questionnaire has not supplied an attribute a condition needs. `IMPLEMENTATIONPLAN
§3.11.6` settles what to do: unknown means the document goes **in**, marked
`undecided`, with the missing attribute named in `unanswered` so the wizard can
turn the guess into an answer. Reading it as «not required» would drop a paper
because nobody had been asked yet — the one failure this subsystem exists to
prevent.

Functions (PROJECT §6.2a):
- `chain_for(db, code)` — a jurisdiction and its ancestors, nearest first.
  Called by: `build_checklist`.
- `build_checklist(db, ...)` — the list itself. Called by: `api/checklist`,
  and later by the MCP tool `build_checklist` (`T7.2`), which must call this and
  not reimplement it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rule_conditions import (
    ConditionAttributeMissing,
    evaluate,
    required_attributes,
)
from app.models.rules import (
    DocumentRequirement,
    Jurisdiction,
    RuleDirection,
    RuleSet,
    RuleStatus,
)

#: How deep a jurisdiction chain may go before we stop climbing. Country →
#: subdivision → city is three; the guard exists because `parent_code` is a
#: self-reference and a cycle introduced by a bad import would otherwise hang a
#: public endpoint rather than return a short list.
MAX_DEPTH = 8


@dataclass
class ChecklistItem:
    """One document, as the person collecting it needs to see it."""

    code: str
    title: str
    issuer: str
    obtained_by: str
    is_mandatory: bool
    valid_for_days: int | None
    lead_time_days: int | None
    #: Which jurisdiction asked for it, and in which direction. Kept because
    #: «кто этого требует» is the first thing anybody disputes, and a merged list
    #: that cannot say loses the argument.
    jurisdiction_code: str
    direction: str
    rule_set_id: str
    #: The last day this can be started and still arrive in time, when the
    #: departure is known. `None` when it is not, or when the requirement names
    #: no lead time.
    start_by: date | None = None
    #: True when `start_by` is already behind us. The single red line on the
    #: screen (owner's decision), and not a rarity: the median horizon on this
    #: market is five days and 31 % of trips are published inside two.
    too_late: bool = False
    #: The questionnaire has not yet supplied an attribute this requirement's
    #: condition asks about, so it is here **because** we do not know
    #: (`IMPLEMENTATIONPLAN §3.11.6`: unknown means include the document). The
    #: screen says «уточните» rather than «обязательно»; the missing attributes
    #: are named in `Checklist.unanswered` under the same code.
    undecided: bool = False


@dataclass
class Checklist:
    items: list[ChecklistItem] = field(default_factory=list)
    #: Requirements that could not be decided because the questionnaire has not
    #: asked yet, as `{code: [attribute, …]}`. Not an error and not an omission —
    #: it is the next question.
    unanswered: dict[str, list[str]] = field(default_factory=dict)
    #: Every attribute any requirement in this corridor mentions. The
    #: questionnaire is computed from the corpus rather than kept by hand beside
    #: it, so a rule that grows a clause grows the form with it.
    asks: list[str] = field(default_factory=list)
    #: Jurisdictions actually consulted, in reading order.
    corridor: list[str] = field(default_factory=list)


async def chain_for(db: AsyncSession, code: str) -> list[str]:
    """`US-NY` → `["US-NY", "US"]`. Nearest jurisdiction first.

    Order is preserved rather than sorted: the city rule is the one that catches
    people out, so it reads first, and the country rule that everybody already
    knows reads last.
    """
    chain: list[str] = []
    current: str | None = code
    while current and len(chain) < MAX_DEPTH:
        row = (
            await db.execute(
                select(Jurisdiction).where(Jurisdiction.code == current)
            )
        ).scalar_one_or_none()
        if row is None:
            break
        chain.append(row.code)
        current = row.parent_code
        if current in chain:  # a bad import made a cycle; stop, do not hang
            break
    return chain


def _stricter(existing: ChecklistItem, incoming: ChecklistItem) -> ChecklistItem:
    """Merge two requirements carrying the same code, toward the stricter side.

    Mandatory beats optional and the longer lead time beats the shorter, because
    the failure modes are not symmetric: a list that over-prepares costs a trip
    to an office, and a list that under-prepares costs the flight.
    """
    existing.is_mandatory = existing.is_mandatory or incoming.is_mandatory
    # An undecided half keeps the whole undecided: the answer is still missing
    # for one of the two jurisdictions asking.
    existing.undecided = existing.undecided or incoming.undecided
    lead = [d for d in (existing.lead_time_days, incoming.lead_time_days) if d is not None]
    existing.lead_time_days = max(lead) if lead else None
    # Validity is the mirror image: the *shortest* window is the binding one,
    # because a certificate that expired for one jurisdiction has expired.
    valid = [d for d in (existing.valid_for_days, incoming.valid_for_days) if d is not None]
    existing.valid_for_days = min(valid) if valid else None
    return existing


async def build_checklist(
    db: AsyncSession,
    *,
    origin: str,
    destination: str,
    category: str,
    attrs: dict,
    transit: list[str] | None = None,
    depart_at: date | None = None,
) -> Checklist:
    """The documents this corridor asks for, in the order they must be started.

    `origin` and `destination` are jurisdiction codes, not airports: the corpus
    is written about places that legislate. `transit` is every jurisdiction the
    route passes through — on the founding corridor there is always at least one,
    because there are no direct Russia → US flights.

    Only `published` sets are consulted. A draft is somebody's work in progress
    and an `outdated` one is a rule that has been superseded; either of them in a
    traveller's list would be the platform stating something it has withdrawn.
    """
    result = Checklist()

    # Export from the origin, transit through the middle, import at the end.
    # Written as a list of (jurisdiction, direction) pairs rather than three
    # loops, so the reading order is the order of the journey.
    legs: list[tuple[str, RuleDirection]] = [(origin, RuleDirection.export)]
    legs += [(code, RuleDirection.transit) for code in (transit or [])]
    legs.append((destination, RuleDirection.import_))

    seen: dict[str, ChecklistItem] = {}
    asks: set[str] = set()

    for place, direction in legs:
        for code in await chain_for(db, place):
            if code not in result.corridor:
                result.corridor.append(code)
            sets = (
                (
                    await db.execute(
                        select(RuleSet).where(
                            RuleSet.jurisdiction_code == code,
                            RuleSet.direction == direction,
                            RuleSet.category_key == category,
                            RuleSet.status == RuleStatus.published,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for rule_set in sets:
                reqs = (
                    (
                        await db.execute(
                            select(DocumentRequirement).where(
                                DocumentRequirement.rule_set_id == rule_set.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for req in reqs:
                    asks |= required_attributes(req.condition)
                    undecided = False
                    try:
                        needed = evaluate(req.condition, attrs)
                    except ConditionAttributeMissing as missing:
                        # `IMPLEMENTATIONPLAN §3.11.6`: unknown decides
                        # **strictly** — the document goes in. Excluding it would
                        # drop a required paper because nobody had been asked
                        # yet, which is the one failure this subsystem exists to
                        # prevent. The attribute is named alongside so the
                        # questionnaire can turn the guess into an answer.
                        needed, undecided = True, True
                        result.unanswered.setdefault(req.code, [])
                        if str(missing.attr) not in result.unanswered[req.code]:
                            result.unanswered[req.code].append(str(missing.attr))
                    if not needed:
                        continue
                    item = ChecklistItem(
                        code=req.code,
                        title=req.title,
                        issuer=req.issuer,
                        obtained_by=req.obtained_by.value,
                        is_mandatory=req.is_mandatory,
                        valid_for_days=req.valid_for_days,
                        lead_time_days=req.lead_time_days,
                        jurisdiction_code=code,
                        direction=direction.value,
                        rule_set_id=str(rule_set.id),
                        undecided=undecided,
                    )
                    if req.code in seen:
                        _stricter(seen[req.code], item)
                    else:
                        seen[req.code] = item

    # The countdown. `depart_at − lead_time_days` is the last day this can be
    # started, and a date already behind us is the one red line on the screen.
    today = date.today()
    for item in seen.values():
        if depart_at is not None and item.lead_time_days is not None:
            item.start_by = depart_at - timedelta(days=item.lead_time_days)
            item.too_late = item.start_by < today

    # Sorted by when they have to be started, soonest first; the ones with no
    # lead time fall to the end, because «no deadline» is not «due first».
    result.items = sorted(
        seen.values(),
        key=lambda i: (
            i.start_by is None,
            i.start_by or today,
            not i.is_mandatory,
            i.code,
        ),
    )
    result.asks = sorted(asks)
    return result
