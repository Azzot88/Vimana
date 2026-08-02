"""T_TRUST.1 — the evidence-decay scale (`D-EVIDENCE-DECAYS`).

The scale is a product decision, so these tests pin the decision itself: the
five anchor points the owner named, the floor, and the two directions the curve
must never go. A formula change that keeps the shape but moves "one year" from
0.70 to 0.50 is a different promise to users, and it should fail here rather
than quietly re-rank everyone on the next deploy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.freshness import (
    FRESHNESS_ANCHORS,
    FRESHNESS_FLOOR,
    age_days,
    freshness_factor,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _at(days: float) -> datetime:
    return NOW - timedelta(days=days)


@pytest.mark.parametrize("days,expected", FRESHNESS_ANCHORS)
def test_the_named_points_are_exact(days, expected):
    """The owner's five points, read back off the curve."""
    assert freshness_factor(_at(days), now=NOW) == pytest.approx(expected)


def test_a_week_is_still_yesterday():
    """Full strength across the whole first week — "вчера" and "неделю назад"
    were called equally strong, so the curve starts flat rather than sloping
    from the first hour."""
    assert freshness_factor(NOW, now=NOW) == 1.0
    assert freshness_factor(_at(3), now=NOW) == 1.0
    assert freshness_factor(_at(7), now=NOW) == 1.0


def test_it_only_ever_goes_down():
    previous = 1.1
    for days in (0, 1, 7, 15, 30, 100, 365, 900, 1825, 3650, 36500):
        value = freshness_factor(_at(days), now=NOW)
        assert value <= previous, f"went up at {days} days"
        previous = value


def test_it_never_goes_below_the_floor():
    for days in (1825, 3650, 100_000):
        assert freshness_factor(_at(days), now=NOW) == FRESHNESS_FLOOR


def test_the_floor_is_not_zero():
    """A verification that happened did happen. Zero would assert that the
    meeting never took place, and make an old badge indistinguishable from a
    forged one — what decays is how much weight to put on it today."""
    assert FRESHNESS_FLOOR > 0


def test_undated_evidence_is_worth_the_floor_not_full_strength():
    """We cannot say how old it is. Treating an unknown date as "today" would
    let the one case we know least about count for the most."""
    assert freshness_factor(None, now=NOW) == FRESHNESS_FLOOR


def test_a_future_date_is_not_punished():
    """Clock skew is not the user's fault, and the alternative is a badge that
    weakens because a server ran a minute ahead."""
    assert freshness_factor(NOW + timedelta(hours=2), now=NOW) == 1.0


def test_a_naive_datetime_is_read_as_utc():
    """The database hands back tz-aware values, but a fixture or a hand-built
    date must not silently shift by the server's timezone."""
    naive = (NOW - timedelta(days=365)).replace(tzinfo=None)
    assert freshness_factor(naive, now=NOW) == pytest.approx(0.70)


def test_between_anchors_it_interpolates():
    """Midway between 30 days (0.95) and 365 (0.70)."""
    midpoint = _at((30 + 365) / 2)
    assert freshness_factor(midpoint, now=NOW) == pytest.approx((0.95 + 0.70) / 2)


def test_age_days_has_no_opinion_about_missing_dates():
    assert age_days(None, now=NOW) is None
    assert age_days(_at(10), now=NOW) == pytest.approx(10.0)
