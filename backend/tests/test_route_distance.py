"""Great-circle distance between two IATA codes.

Feeds the "long hop" publication rule (T3.12) and the archive aggregates
(T3.19). Both were written up as blocked on structured origin/destination —
they were not: `Trip.origin` already holds an IATA code, and `core/airports.py`
has had a haversine helper since T1.10.
"""
import pytest

from app.core.airports import route_distance_km


def test_known_route():
    """London → New York is ~5570 km great-circle. 2% tolerance covers
    variation between airport coordinate datasets."""
    d = route_distance_km("LHR", "JFK")
    assert d is not None
    assert 5450 < d < 5700


def test_short_route():
    """Haversine exists because the naive arccos formula loses precision on
    close points — check a short one lands sensibly. Tbilisi → Yerevan ~250 km."""
    d = route_distance_km("TBS", "EVN")
    assert d is not None
    assert 200 < d < 320


def test_same_airport_is_zero():
    assert route_distance_km("TBS", "TBS") == pytest.approx(0.0, abs=0.001)


def test_symmetric():
    assert route_distance_km("LHR", "JFK") == pytest.approx(
        route_distance_km("JFK", "LHR")
    )


def test_case_and_whitespace_tolerant():
    """The schema is a plain `str`, so what arrives is not guaranteed tidy."""
    assert route_distance_km(" lhr ", "jfk") == pytest.approx(
        route_distance_km("LHR", "JFK")
    )


@pytest.mark.parametrize(
    "origin,destination",
    [
        ("ZZZ", "JFK"),
        ("LHR", "ZZZ"),
        ("Tbilisi", "Yerevan"),  # city names, not codes — a direct POST could
        ("", "JFK"),
    ],
)
def test_unknown_code_returns_none(origin, destination):
    """None, not an exception: callers ask "how far is this?" and must be able
    to answer "unknown" without the request failing."""
    assert route_distance_km(origin, destination) is None


def test_antipodal_is_near_half_circumference():
    """Sanity bound — nothing on Earth exceeds ~20,015 km great-circle."""
    d = route_distance_km("AKL", "MAD")  # Auckland → Madrid, near-antipodal
    if d is None:
        pytest.skip("one of these airports is absent from the index")
    assert d < 20_100
