"""T_DEAL.1 — хранение перед вручением: сколько суток и на чьи деньги.

Storage is **not** a handover method and **not** a rung of the ladder (owner,
2026-09-20): «это не До востребования — это просто хранение перед этапом
вручения. Состояние этапа — ни расчёта, ни получения. Ожидание, иногда
платное.» It can happen twice in one deal — before the carriage and before the
delivery — and a rung that can come round again is not a rung, so it is a state
the carrier declares on the timeline instead.

What this module owns:
  - `terms_of(payload)` — the storage terms frozen into the agreement.
  - `day_starts_between(...)` — the boundary rule (owner: «Новый день начинается
    утром например в 6 утра»), counted on the storage place's own clock.
  - `accrue(...)` — what the counter shows: until when it is free, how many paid
    days have started, how much that is, and whether the platform's ceiling has
    been reached.

**The counter is advisory, and that is the owner's decision** (2026-09-20):
«счётчик уведомительный, и сумма за хранение может быть изменена». What is owed
is what the carrier declares on `storage.charged` and the paying side confirms —
a parcel handed over at seven in the morning by arrangement should not cost a
day because a clock said so. This module computes the number the two of them
start from, and the card is where the number becomes an obligation.

Named `deal_storage` and not `storage`: `core.storage` is the R2 bucket — the
place attachments live — and one module called «storage» holding both the S3
client and the price of waiting would be a name that answers two questions.

Functions (PROJECT §6.2a):
  - `terms_of`, `accrue`, `state_for_deal` — called by `api.deals.get_deal`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

#: Units a carrier may price storage by (owner, 2026-09-20: «1 доллар за кг (за
#: место) в день»). Both spellings exist in the market and they are not the same
#: sum, so the carrier says which one they mean rather than the platform
#: guessing from the cargo.
STORAGE_UNITS: tuple[str, ...] = ("kg", "place")


@dataclass(frozen=True)
class StorageTerms:
    """What the carrier published, as the deal froze it.

    Frozen into the agreement rather than read from the trip at display time: a
    carrier who edits the tariff in their listing must not change the price of
    a storage that is already running. Same reasoning as `carriage_rules` on
    the deal detail — the rule a deal was struck under is not the current one.
    """

    free_days: int
    price: float
    unit: str
    currency: str

    def as_dict(self) -> dict:
        return {
            "free_days": self.free_days,
            "price": self.price,
            "unit": self.unit,
            "currency": self.currency,
        }


def terms_of(payload: dict | None) -> StorageTerms | None:
    """Read storage terms out of an agreement payload, or `None`.

    Defensive about types because the payload is history: a card written before
    this existed carries nothing, and one written by anything that speaks the
    API carries whatever it sent. A malformed block is read as «no storage
    terms», never as free storage — the absence of a tariff is the absence of
    the service, and inventing a zero here would bill nobody for a real cost.
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("storage_terms")
    if not isinstance(raw, dict):
        return None
    try:
        free_days = int(raw["free_days"])
        price = float(raw["price"])
        unit = str(raw["unit"])
        currency = str(raw["currency"])
    except (KeyError, TypeError, ValueError):
        return None
    if free_days < 0 or price < 0 or unit not in STORAGE_UNITS:
        return None
    return StorageTerms(
        free_days=free_days, price=price, unit=unit, currency=currency
    )


def _local(moment: datetime, tz_offset_minutes: int) -> datetime:
    """The same instant, on the storage place's clock.

    Naive on purpose: what follows only asks «which calendar day is this, and
    has six o'clock passed», and a UTC answer to that question is the wrong
    answer everywhere except one meridian.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(
        minutes=tz_offset_minutes
    )


def day_starts_between(
    start: datetime,
    now: datetime,
    *,
    day_start_hour: int,
    tz_offset_minutes: int = 0,
) -> int:
    """How many storage days have begun since the parcel was put away.

    Owner's rule, 2026-09-20: «Округление по границам суток — новый день
    начинается утром например в 6 утра, позднее вручение по договорённости.»

    So a day is not 24 hours from whenever the carrier pressed the button: it
    is a morning. A parcel stored at midday and collected the next afternoon
    has crossed one morning and counts as one day — and one collected at half
    past six, having crossed the same morning, counts as one day too, which is
    what «позднее вручение по договорённости» is there to forgive. The
    forgiving is the carrier's to do on the card; the clock does not do it
    silently.
    """
    if now <= start:
        return 0
    local_start = _local(start, tz_offset_minutes)
    local_now = _local(now, tz_offset_minutes)
    first = local_start.replace(
        hour=day_start_hour, minute=0, second=0, microsecond=0
    )
    if first <= local_start:
        first += timedelta(days=1)
    if local_now < first:
        return 0
    return (local_now - first).days + 1


def free_until(
    start: datetime,
    *,
    free_days: int,
    day_start_hour: int,
    tz_offset_minutes: int = 0,
) -> datetime:
    """The moment storage stops being free — the (free_days + 1)-th morning.

    Returned in UTC so the screen can render it in the reader's own settings:
    the boundary is local to the parcel, the display is local to the person.
    """
    local_start = _local(start, tz_offset_minutes)
    first = local_start.replace(
        hour=day_start_hour, minute=0, second=0, microsecond=0
    )
    if first <= local_start:
        first += timedelta(days=1)
    local_boundary = first + timedelta(days=free_days)
    return (local_boundary - timedelta(minutes=tz_offset_minutes)).replace(
        tzinfo=timezone.utc
    )


def accrue(
    *,
    started_at: datetime,
    now: datetime,
    terms: StorageTerms,
    units: float | None,
    day_start_hour: int,
    max_paid_days: int,
    tz_offset_minutes: int = 0,
) -> dict:
    """The counter, as both sides see it.

    `units` is the kilograms or the number of places the tariff multiplies. It
    may be `None` — a cargo whose weight nobody stated — and then the sum is
    `None` rather than nought: «мы не знаем, сколько это» is a different answer
    from «это бесплатно», and the second one would quietly cost the carrier
    their fee.

    The ceiling is the platform's (`storage_max_paid_days`, 14 by owner's
    decision 2026-09-20) and it is a **ceiling on what accrues**, not a deadline
    that does something: past it the sum stops growing and the state says so, so
    that an open-ended счётчик cannot outgrow the money an escrow is holding for
    this deal. What happens next is a decision two people take, not one the
    clock takes for them.
    """
    days_begun = day_starts_between(
        started_at,
        now,
        day_start_hour=day_start_hour,
        tz_offset_minutes=tz_offset_minutes,
    )
    paid_days = max(0, days_begun - terms.free_days)
    capped = paid_days > max_paid_days
    billable = min(paid_days, max_paid_days)
    amount = None if units is None else round(billable * terms.price * units, 2)
    return {
        "started_at": started_at,
        "free_days": terms.free_days,
        "free_until": free_until(
            started_at,
            free_days=terms.free_days,
            day_start_hour=day_start_hour,
            tz_offset_minutes=tz_offset_minutes,
        ),
        "days_begun": days_begun,
        "paid_days": billable,
        "price": terms.price,
        "unit": terms.unit,
        "units": units,
        "currency": terms.currency,
        "amount": amount,
        "max_paid_days": max_paid_days,
        "capped": capped,
    }


#: T_DEAL.1 — the cards that end a storage. Nothing is «taken off storage» by
#: hand, and that is deliberate: a button whose only job is to stop a meter is a
#: button people forget, and the meter would then run past the truth. The parcel
#: moving on *is* the end of the waiting, so the next act in the custody chain
#: closes it.
#: `storage.charged` is **not** one of them: the bill is not the end of the
#: waiting. A carrier may charge a first fortnight and go on storing, and a
#: charge that silently closed the state would take the counter off the screen
#: while the parcel is still lying there.
STORAGE_ENDING_KINDS: frozenset[str] = frozenset(
    {
        "handoff.declared",
        "handoff.received",
        "posted.declared",
        "delivery.declared",
        "received.as_expected",
    }
)


async def state_for_deal(
    db: AsyncSession,
    deal_id: uuid.UUID,
    *,
    agreed_payload: dict | None,
    weight_kg: float | None,
    now: datetime | None = None,
) -> dict | None:
    """The storage this deal is in right now, or `None` if it is not in one.

    Reads the timeline rather than a column on the deal: the waiting is already
    a card in the chain (`transit.update` with `stage: storage`), and a second
    record of «is it stored» is a second answer to be wrong. The parcel is in
    storage when the last such declaration is newer than every card that would
    have moved it on.

    Returns the accrual as `core.deal_storage.accrue` computes it, plus `charged` —
    what the carrier has actually billed, once they have. The счётчик is
    advisory (owner, 2026-09-20), so a screen must be able to show both numbers
    without pretending they are the same one.
    """
    from app.core.params import resolve
    from app.models.deal import DealVaultMessage

    terms = terms_of(agreed_payload)
    if terms is None:
        return None

    rows = (
        await db.execute(
            select(DealVaultMessage)
            .where(
                DealVaultMessage.deal_id == deal_id,
                DealVaultMessage.card_kind.in_(
                    {"transit.update", *STORAGE_ENDING_KINDS}
                ),
            )
            .order_by(DealVaultMessage.created_at.desc())
            .limit(60)
        )
    ).scalars().all()

    started: DealVaultMessage | None = None
    charged: dict | None = None
    for row in rows:
        payload = row.card_payload or {}
        if row.card_kind == "storage.charged" and charged is None:
            charged = {
                "days": payload.get("days"),
                "amount": payload.get("amount"),
                "currency": payload.get("currency") or terms.currency,
                "state": row.card_state.value if row.card_state else None,
            }
        if row.card_kind in STORAGE_ENDING_KINDS:
            # Newest first, so the first ender we meet is newer than anything
            # below it: whatever storage may be further down has already ended.
            break
        if row.card_kind == "transit.update" and payload.get("stage") == "storage":
            started = row
            break

    if started is None:
        return None

    state = accrue(
        started_at=started.created_at,
        now=now or datetime.now(timezone.utc),
        terms=terms,
        # T_DEAL.1 — «1 доллар за кг (за место) в день». A tariff by weight
        # needs a weight, and a cargo nobody weighed gives `None` rather than a
        # sum invented from one.
        units=weight_kg if terms.unit == "kg" else 1.0,
        day_start_hour=int(await resolve(db, "storage_day_start_hour")),
        max_paid_days=int(await resolve(db, "storage_max_paid_days")),
        tz_offset_minutes=_offset_of(started.card_payload),
    )
    state["charged"] = charged
    return state


def _offset_of(payload: dict | None) -> int:
    """The storage place's offset from UTC, as the declaration recorded it."""
    if not isinstance(payload, dict):
        return 0
    raw = payload.get("tz_offset_minutes")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0
    return int(raw) if -840 <= raw <= 840 else 0
