"""T_TRUST.1 — how much an old proof is still worth (`D-EVIDENCE-DECAYS`).

All evidence ages. A verification from yesterday and one from five years ago are
not the same claim, and until now the product treated them identically: a badge
either existed or it did not.

## The scale

Owner's decision 2026-07-27, in their words: "вчера — сильная, неделю назад —
сильная, месяц — нормальная, год — под вопросом, пять лет — много воды утекло."
Those five points are the scale, read off directly:

    ≤ 7 days   → 1.00    a week is still "yesterday"
      30 days  → 0.95    "нормальная" — noticeably, not much, weaker
     365 days  → 0.70    "под вопросом"
    1825 days  → 0.40    five years, and the floor

Between the anchors the value is linear in days. Linear, not exponential:
the numbers here are a product judgement about how people read a date, not a
measured decay of anything, and an exponential would dress that judgement up as
physics. Piecewise-linear is also readable — anyone can check "one year ⇒ 0.70"
against the table without evaluating a formula.

## Why there is a floor

0.40, never zero. A verification that happened *did happen*: someone met this
person and put their name on it. Decaying to zero would assert that the meeting
never took place, which is false, and would make an old badge indistinguishable
from a forged one. What decays is how much weight a stranger should put on it
today — not the fact.

## What this multiplies

Never a person's score directly. In UBA it scales the *bonus* a verification
grants, toward the unverified baseline, so an old proof makes someone ordinary —
it never makes them worse than someone who was never verified at all. That
distinction is the whole reason this returns a factor rather than a penalty.
"""
from __future__ import annotations

from datetime import datetime, timezone

#: (age in days, factor). Sorted, first point is the full-strength plateau.
FRESHNESS_ANCHORS: list[tuple[float, float]] = [
    (7.0, 1.00),
    (30.0, 0.95),
    (365.0, 0.70),
    (1825.0, 0.40),
]

#: Below this the curve stops. See "Why there is a floor" above.
FRESHNESS_FLOOR: float = FRESHNESS_ANCHORS[-1][1]


def age_days(at: datetime | None, now: datetime | None = None) -> float | None:
    """Age of a piece of evidence in days, or None if it has no date.

    Naive datetimes are read as UTC — the database hands back tz-aware values,
    but a hand-built one in a test or a fixture should not silently become a
    date offset by the server's timezone.
    """
    if at is None:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    delta = (now or datetime.now(tz=timezone.utc)) - at
    return max(delta.total_seconds() / 86400.0, 0.0)


def freshness_factor(at: datetime | None, now: datetime | None = None) -> float:
    """Weight in [FRESHNESS_FLOOR … 1.0] for evidence dated `at`.

    Undated evidence returns the floor rather than full strength: we cannot say
    how old it is, and treating an unknown date as "today" would let the one
    case we know least about count for the most. Future dates return 1.0 —
    clock skew is not the user's fault, and the alternative is a badge that
    weakens because a server was a minute ahead.
    """
    age = age_days(at, now)
    if age is None:
        return FRESHNESS_FLOOR

    prev_age, prev_factor = 0.0, FRESHNESS_ANCHORS[0][1]
    for anchor_age, anchor_factor in FRESHNESS_ANCHORS:
        if age <= anchor_age:
            if anchor_age == prev_age:
                return anchor_factor
            span = anchor_age - prev_age
            return prev_factor + (anchor_factor - prev_factor) * (age - prev_age) / span
        prev_age, prev_factor = anchor_age, anchor_factor
    return FRESHNESS_FLOOR
