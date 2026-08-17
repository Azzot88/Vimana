"""T3.35 — the deal contract.

What matters here is not that a form saves. It is that both entry points produce
the same normalised numbers, that agreement takes two sides, that a counter
supersedes instead of editing, and that the agreed snapshot stops moving once
it exists.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from tests.conftest import SEED_PASSWORD, make_account, unique_email


@pytest_asyncio.fixture
async def deal(session_maker, seed_carrier, seed_sender, seed_trip):
    """A deal of its own for each test.

    `seed_deal` is session-scoped, and terms accumulate on it: one test agreeing
    a contract would decide what the next test reads back. Order-dependent tests
    fail in the one arrangement nobody runs locally.
    """
    from app.models.deal import Deal, DealStatus
    from app.models.marketplace import Order, OrderStatus

    async with session_maker() as db:
        order = Order(
            sender_id=seed_sender.id,
            recipient_contact="+10000000000",
            origin=seed_trip.origin,
            destination=seed_trip.destination,
            category="document",
            declared_value=100.0,
            currency="USD",
            description="Terms test order",
            status=OrderStatus.matched,
            trip_id=seed_trip.id,
        )
        db.add(order)
        await db.flush()
        d = Deal(
            order_id=order.id,
            trip_id=seed_trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.matched,
        )
        db.add(d)
        await db.commit()
        await db.refresh(d)
        return d


BASE = {
    "weight_kg": 4,
    "price_total": 100,
    "declared_value": 1200,
    "currency": "USD",
    "payment_method": "cash",
}


async def _propose(client, headers, deal_id, **overrides):
    body = {**BASE, **overrides}
    return await client.post(
        f"/api/deals/{deal_id}/terms", headers=headers, json=body
    )


# ── proposing ─────────────────────────────────────────────────────────────


async def test_sender_can_propose(client, sender_headers, deal):
    r = await _propose(client, sender_headers, deal.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["card_kind"] == "terms.proposed"
    assert body["card_state"] == "pending"
    # The answer is owed by the other side, never by the author.
    assert body["requires_ack_by"] == "carrier"


async def test_carrier_can_propose_too(client, carrier_headers, deal):
    """Conditions are the carrier's to dictate, but the sender may open the
    conversation — both paths land on the same card."""
    r = await _propose(client, carrier_headers, deal.id)
    assert r.status_code == 201, r.text
    assert r.json()["requires_ack_by"] == "sender"


async def test_outsider_cannot_propose(client, deal):
    email = unique_email("terms-out")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Out"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await _propose(client, hdr, deal.id)
    assert r.status_code in (403, 404), r.text


async def test_proposal_on_missing_deal_is_404(client, sender_headers):
    r = await _propose(client, sender_headers, uuid.uuid4())
    assert r.status_code == 404


# ── normalisation ─────────────────────────────────────────────────────────


async def test_normalised_view_is_computed(client, sender_headers, deal):
    r = await _propose(client, sender_headers, deal.id, weight_kg=4, price_total=100)
    norm = r.json()["payload"]["normalized"]
    assert norm["price_per_kg"] == 25.0
    assert norm["chargeable_weight_kg"] == 4
    assert norm["currency"] == "USD"
    assert "route" in norm


async def test_both_entry_points_normalise_identically(
    client, sender_headers, carrier_headers, deal
):
    """The whole point of normalising server-side: two paths, one answer."""
    a = await _propose(client, sender_headers, deal.id)
    b = await _propose(client, carrier_headers, deal.id)
    assert a.json()["payload"]["normalized"] == b.json()["payload"]["normalized"]


async def test_volumetric_weight_wins_when_bulkier(
    client, sender_headers, deal
):
    """A light bulky box is charged by volume — the airline convention, and the
    reason `chargeable_weight_kg` exists separately from `weight_kg`."""
    r = await _propose(
        client,
        sender_headers,
        deal.id,
        weight_kg=1,
        dimensions_cm=[60, 40, 40],  # 96000/5000 = 19.2 kg
        price_total=100,
    )
    norm = r.json()["payload"]["normalized"]
    assert norm["weight_kg"] == 1
    assert norm["chargeable_weight_kg"] > 19
    assert norm["price_per_kg"] < 6


async def test_unknown_airports_give_no_distance_not_an_error(
    client, sender_headers, deal
):
    """The seed trip's route is not a real IATA pair. That is a legitimate
    proposal, and `None` is the honest answer — not a 500."""
    r = await _propose(client, sender_headers, deal.id)
    assert r.status_code == 201
    norm = r.json()["payload"]["normalized"]
    assert norm["distance_km"] is None
    assert norm["price_per_km"] is None


async def test_bad_dimensions_rejected(client, sender_headers, deal):
    r = await _propose(client, sender_headers, deal.id, dimensions_cm=[1, 2])
    assert r.status_code == 422


async def test_zero_price_rejected(client, sender_headers, deal):
    r = await _propose(client, sender_headers, deal.id, price_total=0)
    assert r.status_code == 422


# ── agreeing ──────────────────────────────────────────────────────────────


async def test_agreement_needs_the_other_side(
    client, sender_headers, deal
):
    """Accepting your own proposal is not an agreement."""
    proposal = await _propose(client, sender_headers, deal.id)
    msg_id = proposal.json()["id"]
    r = await client.post(
        f"/api/deals/{deal.id}/dealvault/messages/{msg_id}/ack",
        headers=sender_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 403, r.text


async def test_acceptance_creates_the_contract(
    client, sender_headers, carrier_headers, deal
):
    proposal = await _propose(client, sender_headers, deal.id, price_total=140)
    msg_id = proposal.json()["id"]

    ack = await client.post(
        f"/api/deals/{deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    assert ack.status_code == 200, ack.text

    current = await client.get(f"/api/deals/{deal.id}/terms", headers=sender_headers)
    assert current.status_code == 200
    body = current.json()
    assert body["card_kind"] == "terms.agreed"
    assert body["payload"]["price_total"] == 140
    assert body["payload"]["proposal_id"] == msg_id


async def test_contract_stamps_the_parameter_version(
    client, sender_headers, carrier_headers, deal
):
    """A rate changed tomorrow must not reach back into a deal struck today —
    so the snapshot carries the parameters it was struck under."""
    proposal = await _propose(client, sender_headers, deal.id)
    msg_id = proposal.json()["id"]
    await client.post(
        f"/api/deals/{deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    current = await client.get(f"/api/deals/{deal.id}/terms", headers=sender_headers)
    params = current.json()["payload"]["platform_params"]
    assert "carrier_fee_percent" in params
    assert "escrow_tier1_percent" in params


async def test_decline_leaves_no_contract(
    client, sender_headers, carrier_headers, deal
):
    proposal = await _propose(client, sender_headers, deal.id)
    msg_id = proposal.json()["id"]
    r = await client.post(
        f"/api/deals/{deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "declined"},
    )
    assert r.status_code == 200
    assert r.json()["card_state"] == "declined"


# ── countering ────────────────────────────────────────────────────────────


async def test_counter_supersedes_instead_of_editing(
    client, sender_headers, carrier_headers, deal
):
    """"What was offered before" is exactly the question an arbiter asks, so the
    older card stays in the record."""
    first = await _propose(client, sender_headers, deal.id, price_total=100)
    first_id = first.json()["id"]

    counter = await _propose(
        client,
        carrier_headers,
        deal.id,
        price_total=160,
        supersedes_id=first_id,
    )
    assert counter.status_code == 201, counter.text
    assert counter.json()["card_kind"] == "terms.countered"
    assert counter.json()["supersedes_id"] == first_id
    # The counter now awaits the original proposer.
    assert counter.json()["requires_ack_by"] == "sender"

    listing = await client.get(
        f"/api/deals/{deal.id}/dealvault", headers=sender_headers
    )
    old = next(m for m in listing.json()["items"] if m["id"] == first_id)
    assert old["card_state"] == "superseded"


async def test_cannot_supersede_a_settled_card(
    client, sender_headers, carrier_headers, deal
):
    proposal = await _propose(client, sender_headers, deal.id)
    msg_id = proposal.json()["id"]
    await client.post(
        f"/api/deals/{deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "declined"},
    )
    r = await _propose(
        client, carrier_headers, deal.id, supersedes_id=msg_id
    )
    assert r.status_code == 409, r.text


async def test_superseded_card_cannot_be_answered(
    client, sender_headers, carrier_headers, deal
):
    first = await _propose(client, sender_headers, deal.id)
    first_id = first.json()["id"]
    await _propose(client, carrier_headers, deal.id, supersedes_id=first_id)

    r = await client.post(
        f"/api/deals/{deal.id}/dealvault/messages/{first_id}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 409, r.text


# ── reading ───────────────────────────────────────────────────────────────


async def test_current_terms_returns_pending_before_agreement(
    client, sender_headers, deal
):
    r = await _propose(client, sender_headers, deal.id)
    current = await client.get(
        f"/api/deals/{deal.id}/terms", headers=sender_headers
    )
    assert current.status_code == 200
    assert current.json()["id"] == r.json()["id"]
    assert current.json()["card_state"] == "pending"


async def test_outsider_cannot_read_terms(client, deal):
    email = unique_email("terms-peek")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Peek"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await client.get(f"/api/deals/{deal.id}/terms", headers=hdr)
    assert r.status_code in (403, 404)


# ── the normaliser in isolation ───────────────────────────────────────────


def test_volumetric_helper_ignores_unmeasured():
    """`None` is not zero — an unmeasured box must never win a max()."""
    from app.core.terms import volumetric_weight_kg

    assert volumetric_weight_kg(None, 5000) is None
    assert volumetric_weight_kg([10, 10], 5000) is None
    assert volumetric_weight_kg([0, 10, 10], 5000) is None
    assert volumetric_weight_kg([50, 40, 30], 5000) == 12.0


def test_corridor_of_real_airports():
    from app.core.airports import corridor_of

    assert corridor_of("DXB", "JFK") == "AE->US"
    assert corridor_of("NOPE", "JFK") is None
