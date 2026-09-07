"""T3.35 — the carrier's baseline terms on a trip.

Until `0051` a trip had a route, a date and a capacity and no price at all, so
every deal invented one in chat and nothing was comparable between two trips on
the same corridor. These tests hold the shape of that baseline: optional, but
validated when given, and visible in the listing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _payload(**overrides):
    body = {
        # T3.11.15 — the route is a chain on the wire. A one-leg chain is the
        # ordinary case and stays as short to write as the old flat trio.
        "legs": [
            {
                "origin": "DXB",
                "destination": "JFK",
                "depart_at": (
                    datetime.now(timezone.utc) + timedelta(days=6)
                ).isoformat(),
            }
        ],
        "capacity": 6.0,
        "allowed_categories": ["document"],
    }
    body.update(overrides)
    return body


async def test_trip_without_a_price_is_valid(client, carrier_headers):
    """"Price on request" is a real listing, not a missing field. Forcing a
    number would make carriers invent one to get past the form."""
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    assert r.status_code == 201, r.text
    assert r.json()["price_per_kg"] is None
    assert r.json()["currency"] == "USD"


async def test_baseline_terms_are_stored_and_returned(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(
            price_per_kg=25,
            min_deal_price=40,
            currency="eur",
            max_declared_value=5000,
            # T3.11.15 — the single `allowed_handover_methods` list is gone; the
            # trip states each end of the handover separately.
            handover_origin={"methods": ["in_person", "courier"], "points": []},
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["price_per_kg"] == 25
    assert body["min_deal_price"] == 40
    # Lower-cased on the way in — the currency is a code, not free text.
    assert body["currency"] == "EUR"
    assert body["max_declared_value"] == 5000
    assert body["handover_origin"]["methods"] == ["in_person", "courier"]


async def test_negative_price_rejected(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(price_per_kg=-1)
    )
    assert r.status_code == 422


async def test_zero_price_rejected(client, carrier_headers):
    """Zero is not "free", it is a number nobody meant to type."""
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(price_per_kg=0)
    )
    assert r.status_code == 422


async def test_unknown_handover_method_rejected(client, carrier_headers):
    """The list has to match the one the cards use, or a carrier advertises a
    method no card can ever name."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_payload(handover_origin={"methods": ["teleport"], "points": []}),
    )
    assert r.status_code == 422


async def test_currency_must_be_a_code_we_know(client, carrier_headers):
    """Three or four characters, and one of ours.

    `DOLLAR` is refused by the length; `RUUB` gets past it and is refused by the
    list — which is the case that matters, because a typo in a currency code is
    a price nobody can compare.
    """
    for bad in ("DOLLAR", "RUUB"):
        r = await client.post(
            "/api/trips", headers=carrier_headers, json=_payload(currency=bad)
        )
        assert r.status_code == 422, f"{bad}: {r.text}"


async def test_four_character_stablecoin_publishes(client, carrier_headers):
    """`USDT` is four characters, and the column and schema were both three.

    A carrier whose primary currency is a stablecoin picks it in the profile and
    publishes with it — the setting and the form have to agree, or the setting
    exists and does nothing.
    """
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(currency="usdt")
    )
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "USDT"


async def test_baseline_shows_up_in_the_listing(client, carrier_headers):
    """The point of storing it: comparing two trips before opening a chat."""
    created = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(price_per_kg=31)
    )
    trip_id = created.json()["id"]

    listing = await client.get("/api/trips", headers=carrier_headers)
    assert listing.status_code == 200
    mine = next((t for t in listing.json()["items"] if t["id"] == trip_id), None)
    assert mine is not None
    assert mine["price_per_kg"] == 31


async def test_proposal_flags_a_price_below_the_carrier_minimum(
    client, carrier_headers, sender_headers, session_maker, seed_carrier, seed_sender
):
    """Not an error — the carrier may still accept — but the card says so, so
    nobody agrees to a number they had already ruled out."""
    from app.models.deal import Deal, DealStatus
    from app.models.marketplace import Order, OrderStatus, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="DXB",
            destination="JFK",
            depart_at=datetime.now(timezone.utc) + timedelta(days=6),
            capacity=6.0,
            status=TripStatus.open,
            price_per_kg=25.0,
            min_deal_price=200.0,
            currency="USD",
        )
        db.add(trip)
        await db.flush()
        order = Order(
            sender_id=seed_sender.id,
            recipient_contact="+10000000000",
            origin=trip.origin,
            destination=trip.destination,
            category="document",
            declared_value=900.0,
            currency="USD",
            status=OrderStatus.matched,
            trip_id=trip.id,
        )
        db.add(order)
        await db.flush()
        deal = Deal(
            order_id=order.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.matched,
        )
        db.add(deal)
        await db.commit()
        await db.refresh(deal)

    low = await client.post(
        f"/api/deals/{deal.id}/terms",
        headers=sender_headers,
        json={
            "weight_kg": 2,
            "price_total": 50,
            "declared_value": 900,
            "currency": "USD",
        },
    )
    assert low.status_code == 201, low.text
    assert low.json()["payload"]["below_carrier_minimum"] is True

    ok = await client.post(
        f"/api/deals/{deal.id}/terms",
        headers=sender_headers,
        json={
            "weight_kg": 8,
            "price_total": 250,
            "declared_value": 900,
            "currency": "USD",
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["payload"]["below_carrier_minimum"] is False


# ── T_UX.14 / T_UX.15 — display preferences and carriage rules ────────────


async def test_display_preferences_round_trip(client, carrier_headers):
    r = await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"unit_weight": "lb", "date_format": "us"}
    )
    assert r.status_code == 200, r.text
    me = await client.get("/api/auth/me", headers=carrier_headers)
    assert me.json()["unit_weight"] == "lb"
    assert me.json()["date_format"] == "us"


async def test_unknown_unit_rejected(client, carrier_headers):
    r = await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"unit_weight": "stones"}
    )
    assert r.status_code == 422


async def test_display_preference_cannot_be_nulled(client, carrier_headers):
    """No value is not "no preference" — it is a screen that cannot decide how
    to print a weight."""
    r = await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"unit_weight": None}
    )
    assert r.status_code == 422


async def test_trip_inherits_standing_carriage_rules(client, carrier_headers):
    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"carriage_rules": "No liquids."}
    )
    r = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    assert r.status_code == 201, r.text
    assert r.json()["carriage_rules"] == "No liquids."


async def test_trip_rules_are_a_copy_not_a_reference(client, carrier_headers):
    """The whole reason the text sits on both rows: a rule edited in March must
    not rewrite what a sender read in February."""
    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"carriage_rules": "Version one."}
    )
    created = await client.post("/api/trips", headers=carrier_headers, json=_payload())
    trip_id = created.json()["id"]

    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"carriage_rules": "Version two."}
    )
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert mine["carriage_rules"] == "Version one."


async def test_trip_can_override_with_no_rules(client, carrier_headers):
    """Omitted means "use my template"; an explicit empty string means this
    trip carries none. The two have to stay distinguishable."""
    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"carriage_rules": "Template."}
    )
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(carriage_rules="")
    )
    assert r.status_code == 201, r.text
    assert r.json()["carriage_rules"] == ""


# ── T3.11.07 · the account's currencies ────────────────────────────────────


async def test_currencies_are_stored_and_upper_cased(client, carrier_headers):
    """Upper-cased on the way in, exactly as `TripCreate.currency` is: a code
    stored two ways is a code that matches nothing half the time, and the trip
    form pre-fills from this value."""
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"default_currencies": ["aed", "usdt"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_currencies"] == ["AED", "USDT"]

    back = await client.get("/api/auth/me", headers=carrier_headers)
    assert back.json()["default_currencies"] == ["AED", "USDT"]

    # Put back: the test database is never reset, and a currency left behind
    # would follow this carrier through every later test.
    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": ["USD"]}
    )


async def test_currency_order_is_kept_because_the_first_one_is_the_primary(
    client, carrier_headers
):
    """The screen lists them alphabetically; the account stores them in the
    order chosen. Sorting here would quietly reassign which currency a new trip
    starts in — the one thing this order decides."""
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"default_currencies": ["ZEC", "AED", "PLN"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_currencies"] == ["ZEC", "AED", "PLN"]

    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": ["USD"]}
    )


async def test_repeated_currency_is_kept_once(client, carrier_headers):
    """A double tap in the picker is not an error worth a red box — the second
    copy simply is not a second currency."""
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"default_currencies": ["EUR", "eur", "USD"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["default_currencies"] == ["EUR", "USD"]

    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": ["USD"]}
    )


async def test_unknown_currency_is_refused(client, carrier_headers):
    """A closed list: a typo in a code is a price nobody can compare."""
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"default_currencies": ["USD", "RUUB"]},
    )
    assert r.status_code == 422, r.text

    unchanged = await client.get("/api/auth/me", headers=carrier_headers)
    assert "RUUB" not in unchanged.json()["default_currencies"]


async def test_empty_currency_list_is_refused(client, carrier_headers):
    """Zero currencies is not a preference — it is a trip form with nothing to
    pre-fill. The account keeps whatever it had."""
    r = await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": []}
    )
    assert r.status_code == 422, r.text


async def test_too_many_currencies_are_refused(client, carrier_headers):
    """`MAX_ACCOUNT_CURRENCIES` is what the trip form can show as chips rather
    than as a second dropdown — a list past it is a list nobody reads."""
    from app.core.currencies import CURRENCIES, MAX_ACCOUNT_CURRENCIES

    too_many = list(CURRENCIES[: MAX_ACCOUNT_CURRENCIES + 1])
    r = await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": too_many}
    )
    assert r.status_code == 422, r.text


async def test_currency_preference_does_not_touch_published_trips(
    client, carrier_headers
):
    """A preference decides what an empty form starts with and nothing else.

    The trip keeps what it was published in — changing the account setting
    afterwards must not silently reprice a listing somebody already read.
    """
    published = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(currency="EUR")
    )
    trip_id = published.json()["id"]

    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": ["AED"]}
    )
    listing = await client.get("/api/trips", headers=carrier_headers)
    mine = next(t for t in listing.json()["items"] if t["id"] == trip_id)
    assert mine["currency"] == "EUR"

    await client.patch(
        "/api/auth/me", headers=carrier_headers, json={"default_currencies": ["USD"]}
    )
