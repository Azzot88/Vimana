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
        "origin": "DXB",
        "destination": "JFK",
        "depart_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
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
            allowed_handover_methods=["in_person", "courier"],
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["price_per_kg"] == 25
    assert body["min_deal_price"] == 40
    # Lower-cased on the way in — the currency is a code, not free text.
    assert body["currency"] == "EUR"
    assert body["max_declared_value"] == 5000
    assert body["allowed_handover_methods"] == ["in_person", "courier"]


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
        json=_payload(allowed_handover_methods=["teleport"]),
    )
    assert r.status_code == 422


async def test_currency_must_be_three_letters(client, carrier_headers):
    r = await client.post(
        "/api/trips", headers=carrier_headers, json=_payload(currency="DOLLAR")
    )
    assert r.status_code == 422


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
