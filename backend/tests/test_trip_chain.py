"""T3.11.15 — the trip as a chain, and the two capacities.

The shape these tests pin comes from the analysis of 15 128 real marketplace
messages (TASKS.md, «Разбор переписок рынка (2026-09-06)»): 36.6 % of carrier
posts carry two or more dates, 15.0 % three or more cities, the customs
allowance is reported as a balance that runs out separately from the room in the
bag, "flying in person" sits in the same post as "(a friend is flying)", and
accepting and handing over are routinely arranged differently at the two ends.

The negatives matter more than the happy path here. A chain that stores in the
wrong order, a leg that departs before the one before it, and a capacity whose
two halves collapse into one number are all defects that look like working data
afterwards.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _leg(origin: str, destination: str, days: int) -> dict:
    return {
        "origin": origin,
        "destination": destination,
        "depart_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
    }


def _payload(**overrides):
    body = {"legs": [_leg("DXB", "JFK", 5)], "capacity": 6.0}
    body.update(overrides)
    return body


# ── the chain ─────────────────────────────────────────────────────────────


async def test_three_leg_chain_is_stored_in_order(client, carrier_headers):
    """`Москва — Майами — Лос-Анджелес` in one listing: 15 % of real posts."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            legs=[
                _leg("SVO", "MIA", 5),
                _leg("MIA", "LAX", 7),
                _leg("LAX", "SVO", 12),
            ]
        ),
    )
    assert r.status_code == 201, r.text
    legs = r.json()["legs"]
    assert [leg["order"] for leg in legs] == [0, 1, 2]
    assert [leg["origin"] for leg in legs] == ["SVO", "MIA", "LAX"]


async def test_denormalised_head_comes_from_the_chain(client, carrier_headers):
    """The trio search stands on is derived, so it cannot disagree with the
    legs. Departure is the *first* leg's — that is the moment the cargo has to
    be handed over — and destination is the *last* leg's."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(legs=[_leg("SVO", "IST", 3), _leg("IST", "JFK", 4)]),
    )
    body = r.json()
    assert body["origin"] == "SVO"
    assert body["destination"] == "JFK"
    assert body["depart_at"] == body["legs"][0]["depart_at"]


async def test_codes_are_upper_cased_on_write(client, carrier_headers):
    """T_PERF.1 — the listing filter compares exactly, so a leg stored as `dxb`
    would be invisible to every search for `DXB`."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(legs=[_leg("dxb", "jfk", 5)])
    )
    assert r.json()["legs"][0]["origin"] == "DXB"
    assert r.json()["origin"] == "DXB"


async def test_chain_reaches_the_listing_not_only_the_post_response(
    client, carrier_headers
):
    """The listing builds `TripOut` by hand, so a new field reaches the POST
    response for free and the board only if it is named there. A second flight
    invisible on the board is a second flight nobody can find."""
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(legs=[_leg("SVO", "DXB", 2), _leg("DXB", "SVO", 6)]),
    )
    trip_id = created.json()["id"]
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert len(mine["legs"]) == 2
    assert mine["legs"][1]["destination"] == "SVO"


async def test_legs_may_not_travel_backwards(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(legs=[_leg("SVO", "DXB", 9), _leg("DXB", "SVO", 2)]),
    )
    assert r.status_code == 422, r.text


async def test_two_legs_on_the_same_day_are_accepted(client, carrier_headers):
    """Non-strict on purpose: a carrier who knows the date of the return flight
    but not the hour is ordinary, and refusing them pushes the second flight
    back into a free-text field — the behaviour this model replaces."""
    same_day = _leg("SVO", "DXB", 4)
    back = dict(_leg("DXB", "SVO", 4), depart_at=same_day["depart_at"])
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(legs=[same_day, back])
    )
    assert r.status_code == 201, r.text


async def test_leg_from_a_city_to_itself_is_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(legs=[_leg("DXB", "DXB", 5)])
    )
    assert r.status_code == 422


async def test_trip_without_legs_is_refused(client, carrier_headers):
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload(legs=[]))
    assert r.status_code == 422


async def test_more_than_ten_legs_is_refused(client, carrier_headers):
    legs = [_leg("SVO", "DXB", 1 + i) for i in range(11)]
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload(legs=legs))
    assert r.status_code == 422


# ── the express path ──────────────────────────────────────────────────────


async def test_route_alone_publishes_a_trip(client, carrier_headers):
    """T3.11.07 — the whole express path in one assertion.

    The median carrier on this market publishes five days before departure,
    31 % inside two days and 11.8 % on the day of the flight. Against that
    horizon every required field is a toll, so the route is the only thing a
    carrier must state to become findable.
    """
    r = await client.post(
        "/api/trips", headers=carrier_headers, json={"legs": [_leg("DXB", "JFK", 0)]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["capacity"] is None
    assert body["status"] == "open"


async def test_unstated_weight_stays_unstated(client, carrier_headers):
    """Null is a different answer from a number, and the listing keeps them
    apart rather than printing a zero nobody typed."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json={"legs": [_leg("SVO", "IST", 3)]}
    )
    trip_id = created.json()["id"]
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert mine["capacity"] is None


async def test_stated_weight_is_still_validated(client, carrier_headers):
    """Optional is not unchecked: a negative weight is a wrong claim rather
    than a missing one."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(capacity=-3)
    )
    assert r.status_code == 422


# ── who is flying ─────────────────────────────────────────────────────────


async def test_flown_by_defaults_to_self(client, carrier_headers):
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    assert r.json()["legs"][0]["flown_by"] == "self"


async def test_proxy_leg_is_declared_not_hidden(client, carrier_headers):
    """"#Лечу лично" and "(летит подруга)" appear in the same real post. The
    claim becomes a field so peer verification can apply to whoever crosses the
    border rather than to whoever runs the account."""
    leg = dict(_leg("DXB", "SVO", 5), flown_by="proxy")
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload(legs=[leg]))
    assert r.status_code == 201, r.text
    assert r.json()["legs"][0]["flown_by"] == "proxy"


async def test_unknown_flown_by_is_refused(client, carrier_headers):
    leg = dict(_leg("DXB", "SVO", 5), flown_by="autopilot")
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload(legs=[leg]))
    assert r.status_code == 422


# ── the two capacities ────────────────────────────────────────────────────


async def test_spent_allowance_does_not_close_the_bag(client, carrier_headers):
    """"Лимит на люкс уже занят" sits in posts that still take documents on the
    same flight. The two capacities are independent, and a trip whose allowance
    is spent is still a publishable trip."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            capacity=20.0,
            max_declared_value=10_000,
            declared_value_status="exhausted",
            space_kind="checked_partial",
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["declared_value_status"] == "exhausted"
    assert body["capacity"] == 20.0
    assert body["status"] == "open"


async def test_capacity_state_defaults_to_open(client, carrier_headers):
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    body = r.json()
    assert body["declared_value_status"] == "open"
    assert body["space_kind"] == "unspecified"
    assert body["size_hint"] is None


async def test_size_hint_answers_what_kilograms_do_not(client, carrier_headers):
    """Weight in kg appears in 2.4 % of posts, "small / not big" in 9.9 %."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(size_hint="small")
    )
    assert r.json()["size_hint"] == "small"


async def test_unknown_space_kind_is_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(space_kind="overhead_bin")
    )
    assert r.status_code == 422


async def test_unknown_size_hint_is_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(size_hint="enormous")
    )
    assert r.status_code == 422


async def test_unknown_declared_value_status_is_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(declared_value_status="maybe")
    )
    assert r.status_code == 422


# ── the two ends of the handover ──────────────────────────────────────────


async def test_handover_is_asymmetric(client, carrier_headers):
    """"In Italy I take it at my address or meet in Milan; in Russia I accept a
    courier at home" — one list cannot say that."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_origin={
                "methods": ["in_person"],
                "points": ["Milan", "Turin", "Genoa"],
            },
            handover_destination={"methods": ["courier", "local_post"], "points": []},
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["handover_origin"]["points"] == ["Milan", "Turin", "Genoa"]
    assert body["handover_destination"]["methods"] == ["courier", "local_post"]
    assert body["handover_destination"]["points"] == []


async def test_handover_reaches_the_listing(client, carrier_headers):
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(handover_origin={"methods": ["in_person"], "points": ["Fili"]}),
    )
    trip_id = created.json()["id"]
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert mine["handover_origin"]["points"] == ["Fili"]


async def test_blank_handover_points_are_dropped(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_origin={"methods": [], "points": ["  Fili  ", "", "   "]}
        ),
    )
    assert r.json()["handover_origin"]["points"] == ["Fili"]


async def test_unknown_handover_method_is_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(handover_origin={"methods": ["teleport"], "points": []}),
    )
    assert r.status_code == 422


async def test_too_many_handover_points_are_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_origin={"methods": [], "points": [f"P{i}" for i in range(7)]}
        ),
    )
    assert r.status_code == 422
