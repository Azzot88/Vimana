"""T3.36–T3.39 — logistics, custody, settlement and exceptions as cards.

The catalogue is declarative, so what is worth asserting is that the declaration
is actually enforced: the wrong role cannot raise a card, the wrong side cannot
answer it, a declaration without its photo cannot be confirmed, and the deal
status moves only through a card.
"""
from __future__ import annotations

import base64
import json
import uuid
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


async def _deliver(session_maker, deal_id):
    """Put the deal where money is allowed to be declared.

    T3.11.27 — «Деньги отдаются после получения груза». The settlement tests are
    about who may declare and what closes the deal, not about the order, so they
    start from a parcel that has arrived instead of walking the whole ladder.
    """
    from app.models.deal import Deal, DealStatus

    async with session_maker() as db:
        row = await db.get(Deal, deal_id)
        row.status = DealStatus.delivered
        await db.commit()


async def test_money_is_not_declared_before_the_parcel_arrives(
    client, sender_headers, deal
):
    """The sequence is the protection.

    Nothing here holds the money until Фаза 5, so «груз сначала» is the only
    thing between a sender and a stranger holding both their cash and their
    parcel. The fixture's deal is `accepted` — agreed, nothing carried yet.
    """
    r = await _card(
        client, sender_headers, deal.id, "payment.declared",
        {"amount": 120, "currency": "USD", "method": "cash_on_delivery"},
    )
    assert r.status_code == 409, r.text


async def test_payment_confirmation_closes_the_deal(
    client, session_maker, sender_headers, carrier_headers, deal
):
    """`payment.confirmed` is what separates "said they paid" from "confirmed
    it arrived" — and the deal does not settle without it, even in cash.

    T3.11.27, owner's rule 2026-09-07: «вторая сторона подтверждает такой же
    кнопкой… и сделка закрывается». So the acceptance lands on `closed`, not on
    `confirmed` — the deal does not wait for a further button that nobody was
    ever going to press.

    **Both entries are in the chain, though.** `confirmed` is «деньги
    подтверждены» and `closed` is «делать больше нечего»; a record showing the
    second without the first cannot answer when the payment was agreed, which is
    the one question a settlement dispute opens with.
    """
    import uuid as uuidlib

    from sqlalchemy import select

    from app.models.deal import DealEvent, DealEventType

    await _deliver(session_maker, deal.id)
    declared = await _card(
        client, sender_headers, deal.id, "payment.declared",
        {"amount": 120, "currency": "USD", "method": "cash_on_delivery"},
    )
    assert declared.status_code == 201, declared.text
    assert declared.json()["requires_ack_by"] == "carrier"

    r = await _ack(client, carrier_headers, deal.id, declared.json()["id"])
    assert r.status_code == 200, r.text

    detail = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert detail.json()["status"] == "closed"

    async with session_maker() as db:
        kinds = (
            (
                await db.execute(
                    select(DealEvent.event_type).where(
                        DealEvent.deal_id == uuidlib.UUID(str(deal.id))
                    )
                )
            )
            .scalars()
            .all()
        )
    assert DealEventType.confirmed in kinds
    assert DealEventType.closed in kinds


async def test_carrier_cannot_declare_the_payment(
    client, session_maker, carrier_headers, deal
):
    await _deliver(session_maker, deal.id)
    r = await _card(
        client, carrier_headers, deal.id, "payment.declared", {"amount": 10}
    )
    assert r.status_code == 403, r.text


async def test_payment_amount_must_be_positive(
    client, session_maker, sender_headers, deal
):
    await _deliver(session_maker, deal.id)
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
    # T3.11.27 — `cancelled`, not `closed`. A deal called off is not a deal
    # completed, and a rating built on these words has to tell them apart.
    assert detail.json()["status"] == "cancelled"


async def test_cancellation_carries_its_own_deadline(
    client, sender_headers, session_maker, deal
):
    """The request says when it stops waiting, and the *server* says it.

    A deadline the caller could choose is not a deadline. It is the shorter of
    the two accounts' `cancel_timeout_hours` and the departure — the trip here
    leaves in five days and the accounts keep the 48-hour default, so the
    timeout is what lands, and the cap is asserted as the rule that holds
    whichever of the two is nearer.
    """
    from app.models.marketplace import Trip

    r = await _card(
        client, sender_headers, deal.id, "cancel.requested", {"costs_borne_by": "none"}
    )
    assert r.status_code == 201, r.text
    stamped = r.json()["card_payload"]["expires_at"]
    assert stamped, "a cancellation with no deadline never closes itself"

    when = datetime.fromisoformat(stamped)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    assert when > datetime.now(timezone.utc)

    async with session_maker() as db:
        trip = await db.get(Trip, deal.trip_id)
        depart = trip.depart_at
    if depart.tzinfo is None:
        depart = depart.replace(tzinfo=timezone.utc)
    assert when <= depart


async def test_cancellation_refused_once_the_parcel_moved(
    client, sender_headers, session_maker, deal
):
    """After the handover the question is «where is it», and that is a dispute.

    Accepted mid-flight, a cancellation would close a deal whose cargo is in the
    air and leave the record saying nothing was ever carried.
    """
    from app.models.deal import Deal, DealStatus

    async with session_maker() as db:
        row = await db.get(Deal, deal.id)
        row.status = DealStatus.in_transit
        await db.commit()

    r = await _card(
        client, sender_headers, deal.id, "cancel.requested", {"costs_borne_by": "none"}
    )
    assert r.status_code == 409, r.text


async def test_unanswered_cancellation_closes_itself(
    client, sender_headers, session_maker, deal
):
    """Silence past the deadline is the answer.

    Otherwise a party who simply stops replying keeps the other one's cargo slot
    booked until the plane leaves. The card ends `expired` — nobody accepted it
    — while the deal ends `cancelled`.
    """
    from app.models.deal import CardState, Deal, DealStatus, DealVaultMessage
    from app.tasks.cleanup import _close_stale_cancellations

    r = await _card(
        client, sender_headers, deal.id, "cancel.requested", {"costs_borne_by": "none"}
    )
    assert r.status_code == 201, r.text
    card_id = r.json()["id"]

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    async with session_maker() as db:
        card = await db.get(DealVaultMessage, uuid.UUID(card_id))
        # Reassigned rather than mutated: a JSON column tracks the attribute,
        # not the dict inside it, so an in-place edit is not written back.
        card.card_payload = {**(card.card_payload or {}), "expires_at": past}
        await db.commit()

    assert (await _close_stale_cancellations(50))["closed"] >= 1

    async with session_maker() as db:
        assert (await db.get(Deal, deal.id)).status is DealStatus.cancelled
        card = await db.get(DealVaultMessage, uuid.UUID(card_id))
        assert card.card_state is CardState.expired


async def test_stale_cancellation_lapses_when_the_deal_moved_on(
    client, sender_headers, session_maker, deal
):
    """A request that sat there while the parcel was handed over just lapses.

    Cancelling then would be the platform rewriting an outcome it did not
    witness — so the card expires and the deal is left exactly as it is.
    """
    from app.models.deal import CardState, Deal, DealStatus, DealVaultMessage
    from app.tasks.cleanup import _close_stale_cancellations

    r = await _card(
        client, sender_headers, deal.id, "cancel.requested", {"costs_borne_by": "none"}
    )
    card_id = r.json()["id"]

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    async with session_maker() as db:
        card = await db.get(DealVaultMessage, uuid.UUID(card_id))
        card.card_payload = {**(card.card_payload or {}), "expires_at": past}
        row = await db.get(Deal, deal.id)
        row.status = DealStatus.in_transit
        await db.commit()

    await _close_stale_cancellations(50)

    async with session_maker() as db:
        assert (await db.get(Deal, deal.id)).status is DealStatus.in_transit
        card = await db.get(DealVaultMessage, uuid.UUID(card_id))
        assert card.card_state is CardState.expired


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


# ── platform-side events reach the record too ─────────────────────────────


async def test_dispute_leaves_a_card_in_the_vault(
    client, sender_headers, deal
):
    """T3.39 — a status change with no card behind it reads, to whoever is in
    the chat, as the conversation simply stopping."""
    r = await client.post(
        f"/api/deals/{deal.id}/dispute",
        headers=sender_headers,
        json={"reason": "other", "details": "parcel never arrived"},
    )
    assert r.status_code == 201, r.text

    listing = await client.get(
        f"/api/deals/{deal.id}/dealvault", headers=sender_headers
    )
    kinds = [m["card_kind"] for m in listing.json()["items"]]
    assert "dispute.opened" in kinds


async def test_platform_cards_are_chained(
    client, sender_headers, carrier_headers, deal, session_maker
):
    """The important one. A vault message with no chain entry can be deleted or
    edited without the verifier noticing, and the cards the *server* writes —
    the fixation of price, the seal — are the last ones that should be
    deletable. `_emit` chains for exactly this reason.
    """
    import uuid as uuidlib

    from app.core.deal_chain import verify_content

    proposed = await _card(
        client, sender_headers, deal.id, "pickup.proposed", {"method": "courier"}
    )
    ack = await _ack(client, carrier_headers, deal.id, proposed.json()["id"])
    assert ack.status_code == 200, ack.text

    async with session_maker() as db:
        result = await verify_content(db, uuidlib.UUID(str(deal.id)))

    assert result["content_ok"] is True, result["mismatches"]
    # The emitted half of the step is covered, not just the half a person wrote.
    assert result["checked_messages"] >= 2


# ── T3.11.22 · which service actually carried it ────────────────────────────


async def test_the_card_names_the_service_beside_the_tracking_number(
    client, sender_headers, deal
):
    """T3.11.22 — «какой отправил фактически, рядом с `tracking_number`».

    The trip says what the carrier *can* do; the card says what happened. A
    tracking code without the company that issued it is a string nobody can
    follow, which is why the two belong on one card.
    """
    r = await _card(
        client,
        sender_headers,
        deal.id,
        "dropoff.proposed",
        {
            "method": "local_post",
            "postal_service": "СДЭК",
            "tracking_number": "RU123456789",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["card_payload"]["postal_service"] == "СДЭК"


async def test_a_service_on_a_hand_to_hand_meeting_is_refused(
    client, sender_headers, deal
):
    """Nothing was posted, so nobody carried it. Refused rather than dropped: a
    field silently ignored is a field the sender believes they filled in."""
    r = await _card(
        client,
        sender_headers,
        deal.id,
        "dropoff.proposed",
        {"method": "in_person", "postal_service": "СДЭК"},
    )
    assert r.status_code == 422, r.text


# ── T3.11.17 · the onward postal leg ────────────────────────────────────────


async def test_posting_declares_its_own_leg_not_a_delivery(
    client, sender_headers, carrier_headers, deal
):
    """T3.11.17 — «сдано в почту» is a state of its own.

    44.9 % of carriers post the parcel on inside the destination country, and
    the model knew `handoff` and `received` with nothing between. Accepting this
    card moves the deal to `posted` — not `delivered`, which would be the
    platform asserting something neither party said.
    """
    declared = await _card(
        client,
        carrier_headers,
        deal.id,
        "posted.declared",
        {"postal_service": "СДЭК", "tracking_number": "RU1234567890"},
    )
    assert declared.status_code == 201, declared.text
    msg_id = declared.json()["id"]

    # The evidence is required: a declaration without it is a claim.
    early = await _ack(client, sender_headers, deal.id, msg_id)
    assert early.status_code == 422, early.text

    photo = await _attach_photo(
        client, carrier_headers, deal.id, msg_id, "pre_seal_photo"
    )
    assert photo.status_code == 201, photo.text

    acked = await _ack(client, sender_headers, deal.id, msg_id)
    assert acked.status_code == 200, acked.text

    detail = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert detail.json()["status"] == "posted"

    listing = await client.get(f"/api/deals/{deal.id}/dealvault", headers=sender_headers)
    kinds = [m["card_kind"] for m in listing.json()["items"]]
    assert "posted.confirmed" in kinds


async def test_the_chain_says_which_leg_the_parcel_was_on(
    client, session_maker, sender_headers, carrier_headers, deal
):
    """«Арбитр видит, на какой ноге груз потерялся.»

    Without its own event the record answered «handed over» and «received» and
    left everything between to word against word.
    """
    import uuid as uuidlib

    from sqlalchemy import select

    from app.models.deal import DealEvent, DealEventType

    declared = await _card(
        client,
        carrier_headers,
        deal.id,
        "posted.declared",
        {"postal_service": "USPS", "tracking_number": "US9400100000000000000000"},
    )
    msg_id = declared.json()["id"]
    await _attach_photo(client, carrier_headers, deal.id, msg_id, "pre_seal_photo")
    await _ack(client, sender_headers, deal.id, msg_id)

    async with session_maker() as db:
        events = (
            (
                await db.execute(
                    select(DealEvent).where(
                        DealEvent.deal_id == uuidlib.UUID(str(deal.id)),
                        DealEvent.event_type == DealEventType.posted,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 1


async def test_posting_needs_the_tracking_code_and_the_company(
    client, carrier_headers, deal
):
    """`USERJOURNEY` Этап 4a ends the carrier's responsibility at the code, so a
    declaration without one would end it on their word. The company is required
    with it: a code nobody can attribute is a string, not a way to follow a
    parcel."""
    for payload in (
        {"postal_service": "СДЭК"},
        {"tracking_number": "RU1"},
        {"postal_service": "", "tracking_number": "RU1"},
    ):
        r = await _card(client, carrier_headers, deal.id, "posted.declared", payload)
        assert r.status_code == 422, f"{payload} was accepted"


async def test_only_the_carrier_declares_the_posting(client, sender_headers, deal):
    """The sender is not the one at the post office."""
    r = await _card(
        client,
        sender_headers,
        deal.id,
        "posted.declared",
        {"postal_service": "СДЭК", "tracking_number": "RU1234567890"},
    )
    assert r.status_code == 403, r.text


async def test_deal_detail_carries_what_the_board_form_answered(
    client, sender_headers, deal
):
    """T3.11.27 — «Форма на доске остаётся как есть, карточка подставляется
    заполненной из неё» (owner, 2026-09-07).

    The first version of the agreement opens filled in from these. Asking the
    sender to retype what they typed on the board a minute ago is how the order
    and the agreement end up disagreeing about the same parcel — and it is the
    agreement an arbiter reads.
    """
    r = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["declared_value"] == 1200.0
    assert body["currency"] == "USD"
    # The carrier's own rate, so the card can suggest a total from a weight.
    # A suggestion only: `price_total` is still what the two of them answer.
    assert body["trip_price_per_kg"] == 25.0
    assert "order_deadline" in body


# ── T3.11.17 ч.2 · buying goods to order ──────────────────────────────────


@pytest_asyncio.fixture
async def buyout_deal(session_maker, seed_carrier, seed_sender):
    """A deal on a trip that actually offers to buy goods to order.

    Its own fixture rather than a flag on `deal`: the ceiling is the thing under
    test here, and a trip that offers the service is a different trip.
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
            services=["purchase_on_request"],
            buyout_limit=500.0,
            buyout_paid_by="carrier_credit",
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


_ORDER = {
    "url": "https://shop.example/irrigator",
    "what": "Irrigator",
    "unit_price": 120.0,
    "count": 2,
    "max_total": 260.0,
}


async def test_a_buyout_is_an_object_not_a_conversation(
    client, sender_headers, carrier_headers, buyout_deal
):
    """«Ссылка, что именно берём, сколько стоит, сколько штук, до какой суммы».

    Five parameters, and the fifth is the one the fraud in the market dump turns
    on: each item plausible, no ceiling, and the carrier learns the total after
    their money is gone.
    """
    asked = await _card(
        client, sender_headers, buyout_deal.id, "buyout.requested", _ORDER
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["requires_ack_by"] == "carrier"
    assert asked.json()["card_payload"]["max_total"] == 260.0

    agreed = await _ack(
        client, carrier_headers, buyout_deal.id, asked.json()["id"]
    )
    assert agreed.status_code == 200, agreed.text

    listing = await client.get(
        f"/api/deals/{buyout_deal.id}/dealvault", headers=sender_headers
    )
    assert "buyout.agreed" in [m["card_kind"] for m in listing.json()["items"]]


async def test_a_buyout_cannot_be_asked_of_a_carrier_who_does_not_offer_it(
    client, sender_headers, deal
):
    """The plain `deal` fixture's trip lists no services at all."""
    r = await _card(client, sender_headers, deal.id, "buyout.requested", _ORDER)
    assert r.status_code == 409, r.text


async def test_a_buyout_above_the_carriers_ceiling_is_refused(
    client, sender_headers, buyout_deal
):
    """The limit is the carrier's own, and a sender who talked it up in chat has
    not moved it: it is a standing offer, not something the two negotiated."""
    r = await _card(
        client, sender_headers, buyout_deal.id, "buyout.requested",
        {**_ORDER, "unit_price": 600.0, "count": 1, "max_total": 600.0},
    )
    assert r.status_code == 409, r.text


async def test_a_ceiling_below_the_order_is_refused(
    client, sender_headers, buyout_deal
):
    """A ceiling under `unit_price × count` is a typo, not a ceiling.

    Refused rather than raised to fit: quietly widening somebody's exposure so
    their own numbers agree is the opposite of what the field is for.
    """
    r = await _card(
        client, sender_headers, buyout_deal.id, "buyout.requested",
        {**_ORDER, "max_total": 100.0},
    )
    assert r.status_code == 422, r.text


async def test_only_the_sender_asks_and_only_the_carrier_reports(
    client, sender_headers, carrier_headers, buyout_deal
):
    """The money leaves the carrier's pocket, so they are the one who says it
    did — and the sender acknowledges, because a receipt nobody looked at is a
    claim rather than evidence."""
    wrong_way = await _card(
        client, carrier_headers, buyout_deal.id, "buyout.requested", _ORDER
    )
    assert wrong_way.status_code == 403, wrong_way.text

    bought = await _card(
        client, carrier_headers, buyout_deal.id, "buyout.purchased",
        {"total": 240.0, "currency": "USD"},
    )
    assert bought.status_code == 201, bought.text
    assert bought.json()["requires_ack_by"] == "sender"


async def test_the_purchase_moves_no_status(
    client, sender_headers, carrier_headers, buyout_deal
):
    """Nothing has been carried. Only the carrier's money has moved, and a deal
    that jumped a status here would say the parcel was on its way."""
    bought = await _card(
        client, carrier_headers, buyout_deal.id, "buyout.purchased",
        {"total": 240.0, "currency": "USD"},
    )
    await _ack(client, sender_headers, buyout_deal.id, bought.json()["id"])
    detail = await client.get(
        f"/api/deals/{buyout_deal.id}", headers=sender_headers
    )
    assert detail.json()["status"] == "accepted"


# ── T3.11.27 · both sides can declare the handover ────────────────────────


async def test_the_carrier_can_declare_that_they_took_it(
    client, sender_headers, carrier_headers, deal
):
    """Owner, 2026-09-12: «перевозчик должен подтверждать что получил посылку».

    Whoever is holding the parcel declares; the other confirms. Its own kind
    rather than one shared by both roles, because an arbiter reads these labels
    and «отдал» and «взял» are different claims about who was standing there.
    """
    declared = await _card(client, carrier_headers, deal.id, "handoff.received")
    assert declared.status_code == 201, declared.text
    assert declared.json()["requires_ack_by"] == "sender"

    msg_id = declared.json()["id"]
    await _attach_photo(client, carrier_headers, deal.id, msg_id, "handoff_photo")
    r = await _ack(client, sender_headers, deal.id, msg_id)
    assert r.status_code == 200, r.text

    detail = await client.get(f"/api/deals/{deal.id}", headers=sender_headers)
    assert detail.json()["status"] == "in_transit"


async def test_the_sender_does_not_declare_receipt(client, sender_headers, deal):
    """The parcel is not in their hands, and a claim about somebody else's
    hands is the one thing this record must never carry."""
    r = await _card(client, sender_headers, deal.id, "handoff.received")
    assert r.status_code == 403, r.text


async def test_closing_by_the_pair_seals_the_vault(
    client, session_maker, sender_headers, carrier_headers, deal
):
    """T3.7 — sealing follows the close, wherever the close happens.

    It used to live inside `deals.confirm_deal` alone, so a deal closed by the
    settlement pair stayed open for appends forever. Nobody noticed because the
    only close anybody had walked was the endpoint that also sealed
    (found 2026-09-12).
    """
    import uuid as uuidlib

    from app.models.deal import Deal

    await _deliver(session_maker, deal.id)
    declared = await _card(
        client, sender_headers, deal.id, "payment.declared",
        {"amount": 120, "currency": "USD", "method": "cash_on_delivery"},
    )
    await _ack(client, carrier_headers, deal.id, declared.json()["id"])

    async with session_maker() as db:
        row = await db.get(Deal, uuidlib.UUID(str(deal.id)))
        assert row.status.value == "closed"
        assert row.sealed_at is not None

    # And the vault refuses new content, which is what sealing is for.
    blocked = await _card(
        client, sender_headers, deal.id, "issue.reported", {"category": "delay"}
    )
    assert blocked.status_code == 409, blocked.text


# ── T3.11.27 · the declaration and its evidence are one act ───────────────


async def _card_with_files(client, headers, deal_id, kind, files, payload=None):
    """`POST /cards/with-files` — multipart, several photographs, one card."""
    return await client.post(
        f"/api/deals/{deal_id}/cards/with-files",
        headers=headers,
        files=[("files", (f"p{i}.png", body, "image/png")) for i, body in enumerate(files)],
        data={"kind": kind, "payload": json.dumps(payload or {})},
    )


async def test_a_declaration_arrives_with_its_photographs(
    client, sender_headers, carrier_headers, deal
):
    """Owner, 2026-09-12: «Без фото карточка в чат добавляться не должна.»

    Raised and confirmable in one step: the card comes back already carrying its
    evidence, so the other side can answer it the moment they see it. Before
    this, the two halves were two requests and the second could fail.
    """
    r = await _card_with_files(
        client, sender_headers, deal.id, "handoff.declared",
        [_ONE_PIXEL_PNG, _ONE_PIXEL_PNG],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # Two files, one hash: identical bytes are one file in the safe (T3.11.25),
    # and the card still shows both attachments.
    assert len(body["attachments"]) == 2
    assert body["requires_ack_by"] == "carrier"

    ack = await _ack(client, carrier_headers, deal.id, body["id"])
    assert ack.status_code == 200, ack.text


async def test_a_refused_file_leaves_no_card_behind(
    client, sender_headers, session_maker, deal
):
    """The whole reason this endpoint exists.

    The vault is append-only: a card written before its photograph was accepted
    can never be confirmed (the server refuses the ack without evidence) and can
    never be taken back. So a refusal must happen **before** anything is written
    — not after, which is what two requests could only ever do.
    """
    from sqlalchemy import func, select

    from app.models.deal import DealVaultMessage

    async with session_maker() as db:
        before = (
            await db.execute(
                select(func.count())
                .select_from(DealVaultMessage)
                .where(DealVaultMessage.deal_id == deal.id)
            )
        ).scalar_one()

    r = await client.post(
        f"/api/deals/{deal.id}/cards/with-files",
        headers=sender_headers,
        # A text file wearing an image's name. `validate_upload` opens the bytes
        # rather than trusting the declared type, which is what makes this a 422
        # and not a stored photograph of nothing.
        files=[("files", ("notes.png", b"this is not an image at all", "image/png"))],
        data={"kind": "handoff.declared", "payload": "{}"},
    )
    assert r.status_code == 422, r.text

    async with session_maker() as db:
        after = (
            await db.execute(
                select(func.count())
                .select_from(DealVaultMessage)
                .where(DealVaultMessage.deal_id == deal.id)
            )
        ).scalar_one()
    assert after == before, "a refused photograph must leave no card in the vault"


async def test_the_wrong_kind_of_file_says_what_would_work(
    client, sender_headers, deal
):
    """«Файл не подошёл» was the whole message somebody got. The refusal now
    names what this card takes, because the person holding the file cannot guess
    what their phone called it."""
    r = await client.post(
        f"/api/deals/{deal.id}/cards/with-files",
        headers=sender_headers,
        files=[("files", ("scan.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        data={"kind": "handoff.declared", "payload": "{}"},
    )
    assert r.status_code == 415, r.text
    assert "image/jpeg" in r.json()["detail"]


async def test_a_card_that_needs_no_photo_is_not_raised_here(
    client, sender_headers, deal
):
    """This endpoint is for declarations that stand on evidence. A pickup
    proposal takes none, and accepting files for it would file a photograph
    under a card nobody will ever look at."""
    r = await _card_with_files(
        client, sender_headers, deal.id, "pickup.proposed",
        [_ONE_PIXEL_PNG], {"method": "in_person", "city": "Dubai"},
    )
    assert r.status_code == 422, r.text


async def test_files_are_refused_from_outside_the_deal(client, deal):
    """Party first, bytes second: an outsider must not be able to make the
    server decode their images, let alone store them in this deal."""
    email = unique_email("cards-files-out")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Out"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await _card_with_files(
        client, hdr, deal.id, "handoff.declared", [_ONE_PIXEL_PNG],
    )
    assert r.status_code in (403, 404), r.text
