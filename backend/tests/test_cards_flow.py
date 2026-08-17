"""T3.36–T3.39 — logistics, custody, settlement and exceptions as cards.

The catalogue is declarative, so what is worth asserting is that the declaration
is actually enforced: the wrong role cannot raise a card, the wrong side cannot
answer it, a declaration without its photo cannot be confirmed, and the deal
status moves only through a card.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from tests.conftest import SEED_PASSWORD, make_account, unique_email


@pytest_asyncio.fixture
async def deal(session_maker, seed_carrier, seed_sender):
    """A deal and a trip of their own.

    The trip departs in the future on purpose: `handoff.declared` refuses after
    departure, and a session-wide fixture would make half these tests depend on
    the calendar.
    """
    from app.models.deal import Deal, DealStatus
    from app.models.marketplace import Order, OrderStatus, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="DXB",
            destination="JFK",
            depart_at=datetime.now(timezone.utc) + timedelta(days=5),
            capacity=8.0,
            allowed_categories=["document"],
            status=TripStatus.open,
            price_per_kg=25.0,
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
            declared_value=1200.0,
            currency="USD",
            status=OrderStatus.matched,
            trip_id=trip.id,
        )
        db.add(order)
        await db.flush()
        d = Deal(
            order_id=order.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.accepted,
        )
        db.add(d)
        await db.commit()
        await db.refresh(d)
        return d


async def _card(client, headers, deal_id, kind, payload=None, text=None):
    return await client.post(
        f"/api/deals/{deal_id}/cards",
        headers=headers,
        json={"kind": kind, "payload": payload or {}, "text": text},
    )


async def _ack(client, headers, deal_id, msg_id, decision="accepted"):
    return await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg_id}/ack",
        headers=headers,
        json={"decision": decision},
    )


# A real 1×1 PNG. It has to decode, not merely start with the right magic
# bytes: `validate_upload` (T3.8) opens the image rather than trusting the
# declared MIME type, which is the whole point of that check.
_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _attach_photo(client, headers, deal_id, msg_id, kind):
    """One pixel is enough: the rule under test is "is there evidence", not
    "is the photograph any good"."""
    png = _ONE_PIXEL_PNG
    return await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg_id}/attachments",
        headers=headers,
        files={"file": ("proof.png", png, "image/png")},
        data={"kind": kind},
    )


# ── group 2 · logistics ───────────────────────────────────────────────────


async def test_pickup_proposal_awaits_the_other_side(client, sender_headers, deal):
    r = await _card(
        client, sender_headers, deal.id, "pickup.proposed",
        {"method": "in_person", "city": "Dubai"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["card_state"] == "pending"
    assert r.json()["requires_ack_by"] == "carrier"


async def test_accepting_pickup_emits_the_confirmation(
    client, sender_headers, carrier_headers, deal
):
    """Both halves of a two-sided step end up in the record, rather than one
    card quietly changing colour."""
    proposed = await _card(
        client, sender_headers, deal.id, "pickup.proposed", {"method": "courier"}
    )
    r = await _ack(client, carrier_headers, deal.id, proposed.json()["id"])
    assert r.status_code == 200, r.text

    listing = await client.get(
        f"/api/deals/{deal.id}/dealvault", headers=sender_headers
    )
    kinds = [m["card_kind"] for m in listing.json()["items"]]
    assert "pickup.confirmed" in kinds


async def test_unknown_handover_method_rejected(client, sender_headers, deal):
    r = await _card(
        client, sender_headers, deal.id, "pickup.proposed", {"method": "teleport"}
    )
    assert r.status_code == 422, r.text


async def test_handover_conditions_are_two_sided(
    client, carrier_headers, sender_headers, deal
):
    r = await _card(
        client, carrier_headers, deal.id, "handover.conditions",
        {"fragile": True, "open_on_handover": True},
    )
    assert r.status_code == 201
    assert r.json()["requires_ack_by"] == "sender"


# ── group 3 · custody ─────────────────────────────────────────────────────


async def test_only_the_sender_declares_handoff(client, carrier_headers, deal):
    """The cargo leaves the sender's hands — the carrier cannot announce that
    on their behalf."""
    r = await _card(client, carrier_headers, deal.id, "handoff.declared")
    assert r.status_code == 403, r.text


async def test_handoff_without_photo_cannot_be_confirmed(
    client, sender_headers, carrier_headers, deal
):
    """A declaration without its evidence is a claim."""
    declared = await _card(client, sender_headers, deal.id, "handoff.declared")
    assert declared.status_code == 201
    r = await _ack(client, carrier_headers, deal.id, declared.json()["id"])
    assert r.status_code == 422, r.text


async def test_confirmed_handoff_moves_the_deal_and_fixes_the_terms(
    client, sender_headers, carrier_headers, deal
):
    """The moment the cargo changes hands is the moment the numbers stop
    moving (MASTERPLAN §4.1)."""
    declared = await _card(client, sender_headers, deal.id, "handoff.declared")
    msg_id = declared.json()["id"]
    up = await _attach_photo(
        client, sender_headers, deal.id, msg_id, "handoff_photo"
    )
    assert up.status_code in (200, 201), up.text

    r = await _ack(client, carrier_headers, deal.id, msg_id)
    assert r.status_code == 200, r.text

    detail = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert detail.json()["status"] == "in_transit"

    listing = await client.get(
        f"/api/deals/{deal.id}/dealvault", headers=sender_headers
    )
    fixed = next(
        m for m in listing.json()["items"] if m["card_kind"] == "handoff.confirmed"
    )
    assert "platform_params" in fixed["card_payload"]
    assert "fixed_at" in fixed["card_payload"]


async def test_handoff_after_departure_is_refused_and_asks_to_reconfirm(
    client, sender_headers, session_maker, deal
):
    """A handover after the flight left is not a late handover, it is another
    trip. Silently re-pricing it would turn an agreed deal into a different one.
    """
    from sqlalchemy import update

    from app.models.marketplace import Trip

    async with session_maker() as db:
        await db.execute(
            update(Trip)
            .where(Trip.id == deal.trip_id)
            .values(depart_at=datetime.now(timezone.utc) - timedelta(hours=2))
        )
        await db.commit()

    r = await _card(client, sender_headers, deal.id, "handoff.declared")
    assert r.status_code == 409, r.text

    listing = await client.get(
        f"/api/deals/{deal.id}/dealvault", headers=sender_headers
    )
    kinds = [m["card_kind"] for m in listing.json()["items"]]
    assert "terms.reconfirm_requested" in kinds


async def test_transit_update_is_carrier_only_and_needs_no_answer(
    client, carrier_headers, sender_headers, deal
):
    r = await _card(
        client, carrier_headers, deal.id, "transit.update", {"stage": "departed"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["card_state"] == "accepted"
    assert r.json()["requires_ack_by"] is None

    denied = await _card(
        client, sender_headers, deal.id, "transit.update", {"stage": "arrived"}
    )
    assert denied.status_code == 403


async def test_delivery_is_confirmed_by_the_sender_when_there_is_no_recipient(
    client, carrier_headers, sender_headers, deal
):
    """A deal with no separate recipient is one where the sender is both ends."""
    declared = await _card(
        client, carrier_headers, deal.id, "delivery.declared", {"method": "in_person"}
    )
    assert declared.status_code == 201, declared.text
    assert declared.json()["requires_ack_by"] == "sender"


# ── group 4 · settlement ──────────────────────────────────────────────────


async def test_payment_confirmation_closes_the_deal(
    client, sender_headers, carrier_headers, deal
):
    """`payment.confirmed` is what separates "said they paid" from "confirmed
    it arrived" — and the deal does not reach `confirmed` without it, even in
    cash."""
    declared = await _card(
        client, sender_headers, deal.id, "payment.declared",
        {"amount": 120, "currency": "USD", "method": "cash"},
    )
    assert declared.status_code == 201, declared.text
    assert declared.json()["requires_ack_by"] == "carrier"

    r = await _ack(client, carrier_headers, deal.id, declared.json()["id"])
    assert r.status_code == 200, r.text

    detail = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert detail.json()["status"] == "confirmed"


async def test_carrier_cannot_declare_the_payment(client, carrier_headers, deal):
    r = await _card(
        client, carrier_headers, deal.id, "payment.declared", {"amount": 10}
    )
    assert r.status_code == 403, r.text


async def test_payment_amount_must_be_positive(client, sender_headers, deal):
    r = await _card(
        client, sender_headers, deal.id, "payment.declared", {"amount": 0}
    )
    assert r.status_code == 422


# ── group 5 · exceptions ──────────────────────────────────────────────────


async def test_issue_is_informational(client, sender_headers, deal):
    r = await _card(
        client, sender_headers, deal.id, "issue.reported", {"category": "delay"},
        text="stuck at customs",
    )
    assert r.status_code == 201, r.text
    assert r.json()["requires_ack_by"] is None
    assert r.json()["card_state"] == "accepted"


async def test_unknown_issue_category_rejected(client, sender_headers, deal):
    r = await _card(
        client, sender_headers, deal.id, "issue.reported", {"category": "weather"}
    )
    assert r.status_code == 422


async def test_cancellation_takes_both_sides(
    client, sender_headers, carrier_headers, deal
):
    requested = await _card(
        client, sender_headers, deal.id, "cancel.requested",
        {"costs_borne_by": "split"},
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["requires_ack_by"] == "carrier"

    r = await _ack(client, carrier_headers, deal.id, requested.json()["id"])
    assert r.status_code == 200, r.text

    detail = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert detail.json()["status"] == "closed"


# ── the generic rules ─────────────────────────────────────────────────────


async def test_server_only_card_cannot_be_raised_by_a_party(
    client, sender_headers, deal
):
    r = await _card(client, sender_headers, deal.id, "terms.agreed")
    assert r.status_code == 403, r.text


async def test_unknown_kind_rejected(client, sender_headers, deal):
    r = await _card(client, sender_headers, deal.id, "not.a.card")
    assert r.status_code == 422


async def test_outsider_cannot_raise_a_card(client, deal):
    email = unique_email("cards-out")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Out"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await _card(client, hdr, deal.id, "issue.reported", {"category": "delay"})
    assert r.status_code in (403, 404)


def test_every_kind_still_has_a_spec():
    from app.core.cards import CATALOGUE, CardKind

    for kind in CardKind:
        assert kind in CATALOGUE, kind


def test_only_server_cards_have_no_creator():
    """A card nobody may create and the server never emits is dead weight in the
    catalogue — this catches it before it looks like a feature."""
    from app.core.cards import CATALOGUE

    for kind, spec in CATALOGUE.items():
        if spec.implemented and not spec.creator_roles:
            # Server-emitted ones are fine; they are reached via on_accept_emit
            # or a dedicated endpoint.
            assert spec.ack_by is None or kind.value.startswith("terms."), kind
