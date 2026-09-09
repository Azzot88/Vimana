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
    body = {"payment_model": "cash_on_delivery", "legs": [_leg("DXB", "JFK", 5)], "capacity": 6.0}
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
        "/api/trips", headers=carrier_headers, json={"payment_model": "cash_on_delivery", "legs": [_leg("DXB", "JFK", 0)]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["capacity"] is None
    assert body["status"] == "open"


async def test_unstated_weight_stays_unstated(client, carrier_headers):
    """Null is a different answer from a number, and the listing keeps them
    apart rather than printing a zero nobody typed."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json={"payment_model": "cash_on_delivery", "legs": [_leg("SVO", "IST", 3)]}
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
    is spent is still a publishable trip.

    Since 0064 "spent" is written as a zero rather than as a separate state: the
    number means the allowance **left**, so zero already says it, and a second
    field would be a second place for the same fact to be wrong.
    """
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            capacity=20.0,
            max_declared_value=0,
            space_kind="checked_partial",
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["max_declared_value"] == 0
    assert body["capacity"] == 20.0
    assert body["status"] == "open"


async def test_capacity_defaults_are_unstated(client, carrier_headers):
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    body = r.json()
    assert body["max_declared_value"] is None
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


async def test_negative_customs_allowance_is_refused(client, carrier_headers):
    """The field is "how much is left", and less than nothing is not an amount."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(max_declared_value=-1)
    )
    assert r.status_code == 422


# ── what the carrier will not take ────────────────────────────────────────


async def test_exclusions_are_stored_and_listed(client, carrier_headers):
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(excluded=["tobacco", "luxury"]),
    )
    assert created.status_code == 201, created.text
    assert created.json()["excluded"] == ["tobacco", "luxury"]

    trip_id = created.json()["id"]
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert mine["excluded"] == ["tobacco", "luxury"]


async def test_saying_nothing_is_not_saying_nothing_is_excluded(
    client, carrier_headers
):
    """94 % of this market states no exclusions at all. That silence is `null`,
    not an empty list: an empty list claims the carrier considered the question
    and answered "nothing", which the card would be right to display."""
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    assert r.json()["excluded"] is None


async def test_cash_is_not_in_the_vocabulary(client, carrier_headers):
    """Owner's decision 2026-09-06: the platform takes no position on cash in
    either direction. It was in the list between 0061 and 0062; a client still
    sending it is refused rather than silently ignored."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(excluded=["money"])
    )
    assert r.status_code == 422


async def test_services_are_stored_and_listed(client, carrier_headers):
    """44.9 % of real posts offer onward shipping inside the destination
    country and 19 % marketplace pickup — and until now a sender looking for
    either had nothing to search."""
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(services=["domestic_shipping", "marketplace_pickup"]),
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert mine["services"] == ["domestic_shipping", "marketplace_pickup"]


async def test_unknown_service_is_refused(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(services=["dog_walking"])
    )
    assert r.status_code == 422


async def test_the_settlement_model_must_be_answered(client, carrier_headers):
    """T3.11.07 — obligatory since the owner's decision 2026-09-08.

    The model is stated by 61.7 % of this market anyway, and the sender who has
    to ask about it is the sender who does not book. Three chips is one tap, so
    this does not re-impose the toll `0060` removed when it made weight optional
    for the carrier flying tonight.
    """
    body = _payload()
    body.pop("payment_model")
    r = await client.post("/api/trips", headers=carrier_headers, json=body)
    assert r.status_code == 422, r.text


async def test_each_settlement_model_is_stored_as_given(client, carrier_headers):
    """Three answers, and each survives the round trip.

    They separate *when* the money moves from *where it lives* — the pair that
    actually differs for the two people: cash is settled hand to hand at the
    door, e-money by two phones, the wallet by neither.
    """
    for model in ("cash_on_delivery", "emoney_on_delivery", "platform_wallet"):
        r = await client.post(
            "/api/trips", headers=carrier_headers, json=_payload(payment_model=model)
        )
        assert r.status_code == 201, r.text
        assert r.json()["payment_model"] == model


async def test_unknown_payment_model_is_refused(client, carrier_headers):
    """Every earlier vocabulary is refused rather than quietly stored.

    `escrow`/`prepaid` were the list until `0064`, `on_platform`/`off_platform`
    until `0084`. A client still sending one of them is out of date, and storing
    it would put a word in the carrier's mouth that no screen can print.
    """
    for model in ("barter", "escrow", "prepaid", "on_platform", "off_platform"):
        r = await client.post(
            "/api/trips", headers=carrier_headers, json=_payload(payment_model=model)
        )
        assert r.status_code == 422, model


async def test_transfer_systems_become_a_clean_list(client, carrier_headers):
    """Typed as text and turned into chips by the form, so what arrives is
    whatever the carrier called it. Blanks are dropped rather than refused: a
    trailing comma is a typo, not an answer."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            payment_model="emoney_on_delivery",
            payment_systems=["  Revolut ", "Wise", "", "Wise", "   "],
        ),
    )
    assert r.status_code == 201, r.text
    assert r.json()["payment_systems"] == ["Revolut", "Wise"]


async def test_a_system_named_beside_cash_is_refused(client, carrier_headers):
    """T3.11.07 — the dependent level of `T3.11.22`, applied to money.

    Cash has no system to name, so a system named beside it answers no question.
    Refused rather than dropped: silently discarding what somebody typed is how
    a form teaches people it does not read them.
    """
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(payment_model="cash_on_delivery", payment_systems=["Revolut"]),
    )
    assert r.status_code == 422, r.text


async def test_only_blank_systems_are_the_same_as_none(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            payment_model="emoney_on_delivery", payment_systems=["  ", ""]
        ),
    )
    assert r.json()["payment_systems"] is None



async def test_unknown_exclusion_is_refused(client, carrier_headers):
    """The list is closed on purpose: a free-text refusal produced five
    spellings of "сигареты" and nothing a filter could read."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(excluded=["fireworks"])
    )
    assert r.status_code == 422


async def test_repeated_exclusion_is_deduplicated(client, carrier_headers):
    """A repeat is a client bug, not a carrier saying it twice — and stored it
    would draw the same chip twice on the card."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(excluded=["alcohol", "alcohol", "food"]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["excluded"] == ["alcohol", "food"]


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


# ── the handover ends point at the carrier's own lists ────────────────────


async def _address(client, headers, label="Дом") -> str:
    r = await client.post(
        "/api/me/addresses",
        headers=headers,
        json={"label": label, "country_iso": "RU", "city": "Moscow"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _place(client, headers, text="У метро Фили", country="RU") -> str:
    # T3.11.07 — a country is required on creation since 0072; these tests are
    # about the handover referencing a place, not about where it is.
    r = await client.post(
        "/api/me/meeting-places",
        headers=headers,
        json={"description": text, "country_iso": country},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_handover_points_at_an_address_and_a_place(client, carrier_headers):
    """Ids, not copies of the text: correcting a typo in an address must not
    mean republishing every trip that mentions it."""
    address_id = await _address(client, carrier_headers)
    place_id = await _place(client, carrier_headers)

    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_origin={
                "methods": ["in_person", "courier"],
                "points": [],
                "address_id": address_id,
                "meeting_place_id": place_id,
            }
        ),
    )
    assert r.status_code == 201, r.text
    side = r.json()["handover_origin"]
    assert side["address_id"] == address_id
    assert side["meeting_place_id"] == place_id


async def test_a_stranger_s_address_is_not_found(client, carrier_headers, sender_headers):
    """An unchecked id is a way to publish somebody else's home address on a
    public board. 404 rather than 403, like every other row of theirs."""
    theirs = await _address(client, sender_headers, "Чужой дом")
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_origin={"methods": [], "points": [], "address_id": theirs}
        ),
    )
    assert r.status_code == 404


async def test_a_stranger_s_meeting_place_is_not_found(
    client, carrier_headers, sender_headers
):
    theirs = await _place(client, sender_headers, "Чужое место")
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_destination={
                "methods": [],
                "points": [],
                "meeting_place_id": theirs,
            }
        ),
    )
    assert r.status_code == 404


async def test_postal_services_ride_on_the_destination_side(client, carrier_headers):
    """Third level of the chain, and free strings rather than codes: the
    catalogue has no external source and must not be able to tell a carrier
    that the one company collecting parcels in their town does not exist."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_destination={
                "methods": ["local_post"],
                "points": [],
                "postal_services": ["USPS", "  UPS  ", "USPS", "Тётя Валя с газелью"],
            }
        ),
    )
    assert r.status_code == 201, r.text
    assert r.json()["handover_destination"]["postal_services"] == [
        "USPS",
        "UPS",
        "Тётя Валя с газелью",
    ]


async def test_posting_it_on_implies_the_service(client, carrier_headers):
    """T3.11.22 — the carrier answers once and the coarse level is computed.

    Saying the destination handover is `local_post` **is** saying "I post it on",
    so `domestic_shipping` is derived rather than asked again — and the two can
    no longer disagree.
    """
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_destination={"methods": ["local_post"], "points": []}
        ),
    )
    assert "domestic_shipping" in r.json()["services"]


async def test_no_local_post_no_derived_service(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_destination={"methods": ["in_person"], "points": []}
        ),
    )
    assert r.json()["services"] is None


# ── T3.11.07 · editing a published trip ────────────────────────────────────


async def test_editing_keeps_the_same_trip(client, carrier_headers):
    """The id survives. Cancel-and-republish was the obvious shortcut and it
    changes the id — which is what every inquiry, deal and Nostr event points
    at, so a carrier fixing a departure hour would orphan the conversation they
    were having about it."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(legs=[_leg("DXB", "JFK", 6)])
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["id"]

    edited = await client.patch(
        f"/api/trips/{trip_id}",
        headers=carrier_headers,
        json=_payload(legs=[_leg("DXB", "LHR", 7)], capacity=12.0),
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["id"] == trip_id
    assert body["destination"] == "LHR"
    assert body["capacity"] == 12.0


async def test_editing_replaces_the_whole_chain(client, carrier_headers):
    """Replaced wholesale, not diffed: `leg_order` is dense and assigned on
    write, so matching old rows to new ones would mean guessing which leg the
    carrier meant to keep — and guessing wrong leaves a chain off by one city."""
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            legs=[_leg("SVO", "IST", 5), _leg("IST", "JFK", 6), _leg("JFK", "LAX", 7)]
        ),
    )
    trip_id = created.json()["id"]

    edited = await client.patch(
        f"/api/trips/{trip_id}",
        headers=carrier_headers,
        json=_payload(legs=[_leg("SVO", "DXB", 5)]),
    )
    assert edited.status_code == 200, edited.text
    legs = edited.json()["legs"]
    assert [(leg["origin"], leg["destination"]) for leg in legs] == [("SVO", "DXB")]
    assert [leg["order"] for leg in legs] == [0]


async def test_a_stranger_cannot_edit_a_trip(client, carrier_headers, sender_headers):
    """404, not 403: which trips exist is public, which of them are yours is
    not something a stranger gets to probe."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload()
    )
    trip_id = created.json()["id"]

    r = await client.patch(
        f"/api/trips/{trip_id}", headers=sender_headers, json=_payload()
    )
    assert r.status_code == 404, r.text


async def test_a_cancelled_trip_cannot_be_edited(client, carrier_headers):
    """A trip that is no longer a listing is part of what two people read. The
    way back is a new publication, not a rewrite of the old one."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload()
    )
    trip_id = created.json()["id"]
    cancelled = await client.post(
        f"/api/trips/{trip_id}/cancel", headers=carrier_headers
    )
    assert cancelled.status_code == 200, cancelled.text

    r = await client.patch(
        f"/api/trips/{trip_id}", headers=carrier_headers, json=_payload()
    )
    assert r.status_code == 409, r.text


async def test_editing_validates_the_chain_like_publishing_does(
    client, carrier_headers
):
    """One door, one set of rules. An edit that could store a chain publishing
    refuses would make the validation a formality of the first save."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload()
    )
    trip_id = created.json()["id"]

    r = await client.patch(
        f"/api/trips/{trip_id}",
        headers=carrier_headers,
        json=_payload(legs=[_leg("DXB", "DXB", 6)]),
    )
    assert r.status_code == 422, r.text


async def test_editing_can_grow_the_chain(client, carrier_headers):
    """One flight becomes three. The shape that first broke this: every edit
    reuses `leg_order` 0, and the old row has to be gone before the new one
    lands or `uq_trip_legs_order` refuses it — the delete needs a flush of its
    own, which is not what `delete-orphan` does by itself."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(legs=[_leg("SVO", "DXB", 5)])
    )
    trip_id = created.json()["id"]

    edited = await client.patch(
        f"/api/trips/{trip_id}",
        headers=carrier_headers,
        json=_payload(
            legs=[_leg("SVO", "IST", 5), _leg("IST", "JFK", 6), _leg("JFK", "LAX", 7)]
        ),
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert [leg["order"] for leg in body["legs"]] == [0, 1, 2]
    # The denormalised head and tail follow the new chain, not the old one.
    assert body["origin"] == "SVO"
    assert body["destination"] == "LAX"


async def test_naming_a_service_without_posting_is_refused(client, carrier_headers):
    """T3.11.22 — the third level cannot be answered before the second.

    Three independent answers about the same thing — «отправляю почтой», «выдача
    почтой», «СДЭК» — was the defect: they could disagree and none of them was
    authoritative. The cure is dependence, not deletion: naming the company is
    only possible once posting has been said.
    """
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_destination={
                "methods": ["in_person"],
                "points": [],
                "postal_services": ["CDEK"],
            }
        ),
    )
    assert r.status_code == 422, r.text
    assert "local_post" in r.text


async def test_the_handover_vocabulary_is_declared_once(client, carrier_headers):
    """T3.11.22 — the trip and the deal card read the same list.

    It was written out twice, word for word, in two schema modules with nothing
    connecting them. The place a drift would have surfaced is the worst one: a
    deal card unable to name the method the trip was published with, at the
    moment the parcel changes hands. Asserted here rather than by reading both
    files, because the test has to fail if somebody re-types the list.
    """
    from app.schemas.cards import HANDOVER_METHODS as card_methods
    from app.schemas.marketplace import HANDOVER_METHODS as trip_methods

    assert trip_methods is card_methods

    # And every one of them is publishable, which is what «one vocabulary»
    # actually has to mean for the carrier.
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            handover_origin={"methods": sorted(card_methods), "points": []}
        ),
    )
    assert r.status_code == 201, r.text


# ── T3.11.16 · lifecycle: a listing that has flown is not a listing ─────────


async def test_expiry_is_the_last_leg_not_the_first(client, carrier_headers):
    """T3.11.16 — a trip with a transfer is still a live offer on the day its
    second flight leaves. Retiring it when the first one takes off would hide
    exactly the listings a sender with a transfer route is looking for."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(legs=[_leg("SVO", "IST", 3), _leg("IST", "JFK", 6)]),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["expires_at"][:10] == body["legs"][1]["depart_at"][:10]
    assert body["expires_at"] > body["depart_at"]


async def test_a_flown_trip_leaves_the_board_but_not_my_history(
    client, session_maker, carrier_headers, seed_carrier
):
    """«Рейс с прошедшей датой исчезает из выдачи без ручного действия.»

    Expiry is a filter, not a status change: nobody cancelled the trip and it
    did not fail, it simply happened. Rewriting `status` would put a false word
    into the carrier's own history.
    """
    import uuid as uuidlib

    from sqlalchemy import update as sa_update

    from app.models.marketplace import Trip

    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload()
    )
    trip_id = created.json()["id"]

    async with session_maker() as db:
        await db.execute(
            sa_update(Trip)
            .where(Trip.id == uuidlib.UUID(trip_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await db.commit()

    board = await client.get("/api/trips", params={"origin": "DXB", "limit": 100})
    assert trip_id not in [t["id"] for t in board.json()["items"]]

    mine = await client.get(
        "/api/trips",
        headers=carrier_headers,
        params={"carrier_id": str(seed_carrier.id), "status": "all", "limit": 100},
    )
    assert trip_id in [t["id"] for t in mine.json()["items"]]



async def test_moving_the_flight_tells_the_deals_riding_on_it(
    client, session_maker, monkeypatch, carrier_headers, sender_headers
):
    """T3.11.16 — «перенос перевозчиком», and the deals hear about it.

    On the market this event exists as a line appended to a post («перенесла
    билеты»): not something a sender can act on, and not something the record
    keeps. Here it is an edit that names both dates and reaches the people whose
    delivery rides on them.
    """
    from app.tasks import notifications as notifications_module

    sent: list[tuple] = []

    class _Capture:
        def delay(self, *args, **kwargs):
            sent.append(args)

    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload()
    )
    trip_id = created.json()["id"]
    await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000003333",
                "origin": "DXB",
                "destination": "JFK",
                "category": "document",
                "declared_value": 10.0,
            },
        },
    )

    monkeypatch.setattr(
        notifications_module, "notify_trip_rescheduled", _Capture(), raising=False
    )

    # An edit that does not touch the departure says nothing to anybody: a
    # letter per edit would teach senders to ignore the one that matters. The
    # legs are echoed back **verbatim** — rebuilding them from `_leg()` would
    # move the departure by the milliseconds between two calls, and the test
    # would be asserting the opposite of what it reads.
    same_legs = [
        {
            "origin": leg["origin"],
            "destination": leg["destination"],
            "depart_at": leg["depart_at"],
        }
        for leg in created.json()["legs"]
    ]
    quiet = await client.patch(
        f"/api/trips/{trip_id}",
        headers=carrier_headers,
        json=_payload(legs=same_legs, capacity=9.0),
    )
    assert quiet.status_code == 200, quiet.text
    assert sent == []

    moved = await client.patch(
        f"/api/trips/{trip_id}",
        headers=carrier_headers,
        json=_payload(legs=[_leg("DXB", "JFK", 9)], capacity=9.0),
    )
    assert moved.status_code == 200, moved.text
    assert len(sent) == 1
    assert sent[0][0] == trip_id
    # Both dates travel: the sender's own plans hang off the old one.
    assert sent[0][1] != sent[0][2]


async def test_the_reschedule_letter_names_the_route_and_both_dates(client):
    """The letter is a real one in all six locales, not a status word reused."""
    from app.core.email_templates import LOCALES, render, sample_context

    for locale in LOCALES:
        letter = render("trip_rescheduled", locale, **sample_context("trip_rescheduled"))
        assert letter.subject.strip()
        assert "DXB" in letter.text
        assert "2026-09-15 08:05 UTC" in letter.text
