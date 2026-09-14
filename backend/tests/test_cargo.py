"""T3.12.03 pt.1 — the cargo replaces the order.

`D-CARGO-MODEL` (owner, 2026-09-13): the cargo is created once, before its
first deal, and does not change; the deal carries it and knows its place in the
chain; several facts about the cargo are readings of its deals rather than
columns. These pin exactly those properties.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError
from tests.conftest import SEED_PASSWORD, make_account, unique_email

from app.core.cargo import cargo_location, deal_no, is_last_deal, multihop_deal_count
from app.core.shipment_no import new_shipment_no
from app.models.deal import Deal, DealStatus


async def _open_trip(client, carrier_headers) -> tuple[str, str]:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "legs": [
                {
                    "origin": "CGO",
                    "destination": "CGD",
                    "depart_at": (
                        datetime.now(timezone.utc) + timedelta(days=4)
                    ).isoformat(),
                }
            ],
            "capacity": 3.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], "CGD"


# ── the number ────────────────────────────────────────────────────────────


def test_a_new_number_is_pf_and_eight_digits():
    for _ in range(50):
        assert re.fullmatch(r"PF-\d{3}-\d{5}", new_shipment_no())


def test_a_deal_number_adds_the_position_only_to_the_new_format():
    assert deal_no("PF-482-19375", 1) == "PF-482-19375-1"
    assert deal_no("PF-482-19375", 2) == "PF-482-19375-2"
    # Owner, 2026-09-13: numbers issued before the change are shown as they are.
    assert deal_no("K7M3Q2XA", 1) == "K7M3Q2XA"
    assert deal_no(None, 1) is None


# ── readings, not columns ─────────────────────────────────────────────────


def test_where_the_cargo_is_follows_the_deal_status():
    assert cargo_location(DealStatus.accepted) == "awaiting_carrier"
    assert cargo_location(DealStatus.in_transit) == "in_transit"
    assert cargo_location(DealStatus.posted) == "with_postal_service"
    assert cargo_location(DealStatus.closed) == "delivered"
    assert cargo_location(DealStatus.cancelled) is None
    assert cargo_location("disputed") is None


def test_the_last_deal_is_the_one_whose_recipient_is_final():
    person = uuid.uuid4()
    cargo = SimpleNamespace(final_recipient_id=person)
    assert is_last_deal(SimpleNamespace(recipient_id=person), cargo)
    assert not is_last_deal(SimpleNamespace(recipient_id=uuid.uuid4()), cargo)
    # A chain whose end nobody has named has no last deal yet.
    assert not is_last_deal(
        SimpleNamespace(recipient_id=None), SimpleNamespace(final_recipient_id=None)
    )


# ── the response to a trip ────────────────────────────────────────────────


async def test_responding_to_a_trip_creates_the_cargo_and_its_first_deal(
    client, carrier_headers, sender_headers, session_maker
):
    from app.models.marketplace import Cargo

    trip_id, destination = await _open_trip(client, carrier_headers)
    deadline = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    matched = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "cargo": {
                "category": "document",
                "declared_value": 250.0,
                "description": "a folder",
                "weight_kg": 0.4,
                "dimensions_cm": [30, 22, 2],
                "fragile": True,
                "cargo_url": "https://example.test/item",
            },
            "deadline": deadline.isoformat(),
        },
    )
    assert matched.status_code == 201, matched.text
    deal_id = matched.json()["id"]

    detail = (await client.get(f"/api/deals/{deal_id}", headers=sender_headers)).json()
    assert detail["position"] == 1
    assert re.fullmatch(r"PF-\d{3}-\d{5}", detail["shipment_no"])
    assert detail["deal_no"] == f"{detail['shipment_no']}-1"
    assert detail["cargo_location"] == "awaiting_carrier"
    assert detail["multihop"] is False
    assert detail["deadline"] is not None
    assert "order_id" not in detail

    async with session_maker() as db:
        cargo = await db.get(Cargo, uuid.UUID(detail["cargo_id"]))
        assert cargo.final_destination == destination
        assert cargo.weight_kg == 0.4
        assert cargo.dimensions_cm == [30, 22, 2]
        assert cargo.fragile is True
        assert cargo.cargo_url == "https://example.test/item"
        assert cargo.final_recipient_id is None

    listed = await client.get("/api/deals", headers=sender_headers, params={"limit": 100})
    row = next(d for d in listed.json()["items"] if d["id"] == deal_id)
    assert row["deal_no"] == detail["deal_no"]
    assert row["cargo_category"] == "document"


async def test_no_cargo_can_hold_two_deals_in_one_place(
    session_maker, seed_deal
):
    """Until multi-hop has an API of its own, this constraint is what keeps a
    second deal out of the first one's place."""
    async with session_maker() as db:
        db.add(
            Deal(
                cargo_id=seed_deal.cargo_id,
                position=seed_deal.position,
                trip_id=seed_deal.trip_id,
                sender_id=seed_deal.sender_id,
                carrier_id=seed_deal.carrier_id,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_a_cancelled_deal_does_not_make_a_multihop(
    session_maker, seed_sender, seed_carrier, seed_trip
):
    """Owner, 2026-09-13: a cancelled deal plus a new one is not a chain."""
    from app.models.marketplace import Cargo

    async with session_maker() as db:
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=10.0,
            final_destination="CGD",
        )
        db.add(cargo)
        await db.flush()

        def deal(position, status):
            return Deal(
                cargo_id=cargo.id,
                position=position,
                trip_id=seed_trip.id,
                sender_id=seed_sender.id,
                carrier_id=seed_carrier.id,
                status=status,
            )

        db.add(deal(1, DealStatus.cancelled))
        db.add(deal(2, DealStatus.matched))
        await db.flush()
        assert await multihop_deal_count(db, cargo.id) == 1

        db.add(deal(3, DealStatus.in_transit))
        await db.flush()
        assert await multihop_deal_count(db, cargo.id) == 2
        await db.rollback()


async def test_the_single_deal_s_recipient_becomes_the_final_recipient(
    client, carrier_headers, sender_headers, session_maker
):
    from app.models.marketplace import Cargo

    trip_id, _ = await _open_trip(client, carrier_headers)
    deal_id = (
        await client.post(
            "/api/deals/match",
            headers=sender_headers,
            json={
                "trip_id": trip_id,
                "cargo": {"category": "document", "declared_value": 20.0},
            },
        )
    ).json()["id"]

    email = unique_email("cargo-rcp")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Rcp"})
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    person = (await client.get("/api/auth/me", headers=headers)).json()["id"]

    named = await client.post(
        f"/api/deals/{deal_id}/recipient",
        headers=sender_headers,
        json={"user_id": person},
    )
    assert named.status_code == 201, named.text

    cargo_id = (await client.get(f"/api/deals/{deal_id}", headers=sender_headers)).json()[
        "cargo_id"
    ]
    async with session_maker() as db:
        cargo = await db.get(Cargo, uuid.UUID(cargo_id))
        assert str(cargo.final_recipient_id) == person

    revoked = await client.post(
        f"/api/deals/{deal_id}/participants/{person}/revoke", headers=sender_headers
    )
    assert revoked.status_code == 200, revoked.text
    async with session_maker() as db:
        cargo = await db.get(Cargo, uuid.UUID(cargo_id))
        assert cargo.final_recipient_id is None
