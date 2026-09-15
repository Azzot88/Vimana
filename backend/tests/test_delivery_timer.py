"""T3.12.07 pt.2 — silence after the landing goes to the arbiter.

Owner, 2026-09-14: the clock starts at the landing; the sender is asked once a
day; when nobody confirms within the timer — the sender's own, or the platform's
72 hours — a dispute opens by itself, opened by the platform, and the timer
never confirms anything.

The sweep is run against these tests' own deals only (`deal_ids`): the test
database is never reset, and a sweep over every deal in it would open disputes
on the session's shared ones.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio


@pytest_asyncio.fixture
async def deal(session_maker, seed_carrier, seed_sender):
    from app.models.deal import Deal, DealStatus
    from app.models.marketplace import Cargo, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="DXB",
            destination="JFK",
            # In the future, so the fallback to the flight time never starts
            # the clock: these tests start it with the carrier's landing card.
            depart_at=datetime.now(timezone.utc) + timedelta(days=30),
            capacity=4.0,
            allowed_categories=["document"],
            status=TripStatus.open,
            currency="USD",
        )
        db.add(trip)
        await db.flush()
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=100.0,
            currency="USD",
            final_destination="JFK",
            weight_kg=1.0,
        )
        db.add(cargo)
        await db.flush()
        d = Deal(
            cargo_id=cargo.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.in_transit,
        )
        db.add(d)
        await db.commit()
        await db.refresh(d)
        return d


async def _landed(client, carrier_headers, session_maker, deal, hours_ago: float):
    from app.models.deal import DealVaultMessage

    r = await client.post(
        f"/api/deals/{deal.id}/cards",
        headers=carrier_headers,
        json={"kind": "transit.update", "payload": {"stage": "arrived"}},
    )
    assert r.status_code == 201, r.text
    async with session_maker() as db:
        msg = await db.get(DealVaultMessage, uuid.UUID(r.json()["id"]))
        msg.created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        await db.commit()


async def _sweep(deal):
    from app.tasks.cleanup import _check_delivery_timers

    return await _check_delivery_timers(50, deal_ids=[deal.id])


async def _deal(session_maker, deal):
    from app.models.deal import Deal

    async with session_maker() as db:
        return await db.get(Deal, deal.id)


async def test_nothing_happens_before_the_landing(session_maker, deal):
    assert await _sweep(deal) == {"reminded": 0, "opened": 0}
    assert (await _deal(session_maker, deal)).delivery_reminded_at is None


async def test_the_sender_is_asked_once_a_day(client, carrier_headers, session_maker, deal):
    await _landed(client, carrier_headers, session_maker, deal, hours_ago=2)
    assert (await _sweep(deal))["reminded"] == 0

    await _landed(client, carrier_headers, session_maker, deal, hours_ago=30)
    first = await _sweep(deal)
    assert first == {"reminded": 1, "opened": 0}
    asked_at = (await _deal(session_maker, deal)).delivery_reminded_at
    assert asked_at is not None

    # An hour later is not another day.
    assert (await _sweep(deal))["reminded"] == 0
    assert (await _deal(session_maker, deal)).delivery_reminded_at == asked_at


async def test_silence_past_the_timer_opens_a_dispute_nobody_opened(
    client, carrier_headers, session_maker, deal
):
    from sqlalchemy import select

    from app.core.deal_chain import verify_chain
    from app.models.deal import DealEvent, DealEventType, DealStatus, Dispute

    await _landed(client, carrier_headers, session_maker, deal, hours_ago=80)
    assert (await _sweep(deal))["opened"] == 1

    async with session_maker() as db:
        row = await db.get(type(deal), deal.id)
        assert row.status is DealStatus.disputed
        dispute = (
            await db.execute(select(Dispute).where(Dispute.deal_id == deal.id))
        ).scalar_one()
        assert dispute.opened_by is None
        opened = (
            await db.execute(
                select(DealEvent).where(
                    DealEvent.deal_id == deal.id,
                    DealEvent.event_type == DealEventType.dispute_opened,
                )
            )
        ).scalar_one()
        assert opened.actor_id is None
        assert (await verify_chain(db, deal.id))["ok"] is True

    # Once is enough: the next sweep finds the deal disputed and leaves it.
    assert (await _sweep(deal))["opened"] == 0


async def test_the_sender_s_own_timer_is_the_one_that_counts(
    client, carrier_headers, session_maker, seed_sender, deal
):
    from app.models.deal import DealStatus
    from app.models.user import User

    await _landed(client, carrier_headers, session_maker, deal, hours_ago=30)
    async with session_maker() as db:
        (await db.get(User, seed_sender.id)).delivery_timeout_hours = 24
        await db.commit()
    try:
        assert (await _sweep(deal))["opened"] == 1
        assert (await _deal(session_maker, deal)).status is DealStatus.disputed
    finally:
        # The seed sender is shared across the suite.
        async with session_maker() as db:
            (await db.get(User, seed_sender.id)).delivery_timeout_hours = None
            await db.commit()


async def test_a_deal_that_moved_on_is_left_alone(
    client, carrier_headers, session_maker, deal
):
    """The timer escalates silence; it never confirms a step and never touches a
    deal somebody already answered."""
    from app.models.deal import Deal, DealStatus

    await _landed(client, carrier_headers, session_maker, deal, hours_ago=100)
    async with session_maker() as db:
        (await db.get(Deal, deal.id)).status = DealStatus.closed
        await db.commit()
    assert await _sweep(deal) == {"reminded": 0, "opened": 0}
    assert (await _deal(session_maker, deal)).status is DealStatus.closed


async def test_the_timer_is_a_setting_of_the_account(client, sender_headers):
    r = await client.patch(
        "/api/auth/me", headers=sender_headers, json={"delivery_timeout_hours": 48}
    )
    assert r.status_code == 200, r.text
    assert r.json()["delivery_timeout_hours"] == 48
    back = await client.patch(
        "/api/auth/me", headers=sender_headers, json={"delivery_timeout_hours": None}
    )
    assert back.json()["delivery_timeout_hours"] is None
    too_short = await client.patch(
        "/api/auth/me", headers=sender_headers, json={"delivery_timeout_hours": 1}
    )
    assert too_short.status_code == 422
