"""T_DEAL.1 — хранение перед вручением.

Owner, 2026-09-20: «Это не До востребования — это просто хранение перед этапом
вручения. Состояние этапа — ни расчёта, ни получения. Ожидание, иногда платное.
Должен быть счётчик времени… Потолок хранения 14 дней. Округление по границам
суток — новый день начинается утром например в 6 утра, позднее вручение по
договорённости. У перевозчика есть возможность добавить в сделку количество
суток хранения по факту, отличающееся от счётчика.»

Four rules, and each of them is a way to get the money wrong:
  - a day is a **morning**, not twenty-four hours from a button press;
  - the free period is counted in the same mornings;
  - the accrual stops at the platform's ceiling, so an open-ended counter
    cannot outgrow what an escrow is holding for this deal;
  - the counter is advisory — what is owed is the card the carrier raises and
    the other side answers.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio

from app.core.deal_storage import (
    StorageTerms,
    accrue,
    nights_of_storage,
    terms_of,
)

DAY_START = 6
TARIFF = StorageTerms(free_days=2, price=1.0, unit="kg", currency="USD")


def _at(day: int, hour: int) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc)


def test_a_night_spent_here_is_a_day_charged():
    """Stored at noon, asked about at eleven the next morning: one night has
    been spent, so it is one day — even though it is 23 hours."""
    assert nights_of_storage(_at(1, 12), _at(2, 11), day_start_hour=DAY_START) == 1


def test_a_parcel_collected_before_the_morning_has_cost_no_night():
    """Stored at noon, asked about at five the next morning: the morning that
    ends the first night has not come.

    Owner, 2026-09-20: «Ночь пролежало — один день». A hotel counts what it
    sold — the room overnight — and so does a warehouse; a parcel dropped off
    at noon and collected the same evening has cost nobody a night."""
    assert nights_of_storage(_at(1, 12), _at(2, 5), day_start_hour=DAY_START) == 0


def test_the_boundary_is_local_to_the_parcel():
    """Six in the morning in Dubai is two in the morning in UTC.

    Without the offset the boundary lands four hours late, and a parcel
    collected at half past six local would be billed for a day that, by the
    server's clock, had not started. The carrier's device reports the offset
    when they declare the storage.
    """
    dubai = 4 * 60
    # 01:30 UTC on the 2nd is 05:30 in Dubai — the night has not ended yet.
    assert (
        nights_of_storage(
            _at(1, 12),
            datetime(2026, 9, 2, 1, 30, tzinfo=timezone.utc),
            day_start_hour=DAY_START,
            tz_offset_minutes=dubai,
        )
        == 0
    )
    # 02:30 UTC is 06:30 in Dubai — the morning has come, and the night counts.
    assert (
        nights_of_storage(
            _at(1, 12),
            datetime(2026, 9, 2, 2, 30, tzinfo=timezone.utc),
            day_start_hour=DAY_START,
            tz_offset_minutes=dubai,
        )
        == 1
    )


def test_the_free_nights_come_first_and_cost_nothing():
    """«До 2-х дней хранение бесплатное» — two nights, then the meter."""
    state = accrue(
        started_at=_at(1, 12),
        now=_at(3, 12),  # two nights spent, the last of them free
        terms=TARIFF,
        units=3.0,
        day_start_hour=DAY_START,
        max_paid_days=14,
    )
    assert state["nights"] == 2
    assert state["paid_days"] == 0
    assert state["amount"] == 0


def test_the_third_night_is_the_first_paid_one():
    state = accrue(
        started_at=_at(1, 12),
        now=_at(4, 12),
        terms=TARIFF,
        units=3.0,
        day_start_hour=DAY_START,
        max_paid_days=14,
    )
    assert state["paid_days"] == 1
    # «1 доллар за кг в день», three kilograms.
    assert state["amount"] == 3.0
    assert state["currency"] == "USD"


def test_free_until_is_the_morning_the_charging_starts():
    state = accrue(
        started_at=_at(1, 12),
        now=_at(2, 0),
        terms=TARIFF,
        units=1.0,
        day_start_hour=DAY_START,
        max_paid_days=14,
    )
    # Arrived on the 1st at noon: the first night ends on the 2nd at six, the
    # second on the 3rd — so the third night, the first paid one, starts being
    # charged at the morning of the 4th.
    assert state["free_until"] == _at(4, 6)


def test_the_ceiling_stops_the_sum_and_says_so():
    """Owner, 2026-09-20: «Потолок хранения 14 дней».

    Not a deadline that does something — nothing is disposed of and nobody is
    thrown out — but the point past which the счётчик stops growing. An
    accrual without a ceiling is an obligation an escrow cannot cover, and this
    is the number that keeps the two in the same order of magnitude.
    """
    state = accrue(
        started_at=_at(1, 12),
        now=_at(1, 12) + timedelta(days=40),
        terms=TARIFF,
        units=2.0,
        day_start_hour=DAY_START,
        max_paid_days=14,
    )
    assert state["paid_days"] == 14
    assert state["amount"] == 28.0
    assert state["capped"] is True


def test_a_cargo_nobody_weighed_gives_no_sum_rather_than_nought():
    """`None` and `0` are different answers, and the second one is a free
    storage nobody agreed to."""
    state = accrue(
        started_at=_at(1, 12),
        now=_at(6, 12),
        terms=TARIFF,
        units=None,
        day_start_hour=DAY_START,
        max_paid_days=14,
    )
    assert state["paid_days"] == 3
    assert state["amount"] is None


def test_half_a_tariff_is_not_a_tariff():
    """A payload missing the price, or carrying a unit nobody sells by, reads
    as «this carrier does not store» — never as free storage."""
    assert terms_of({"storage_terms": {"free_days": 2, "unit": "kg"}}) is None
    assert (
        terms_of(
            {"storage_terms": {"free_days": 2, "price": 1, "unit": "box", "currency": "USD"}}
        )
        is None
    )
    assert terms_of({}) is None
    assert terms_of(None) is None


def test_a_whole_tariff_is_read_back_as_it_was_written():
    read = terms_of(
        {"storage_terms": {"free_days": 0, "price": 2.5, "unit": "place", "currency": "EUR"}}
    )
    assert read == StorageTerms(
        free_days=0, price=2.5, unit="place", currency="EUR"
    )


# ── the deal's own storage, end to end ────────────────────────────────────


@pytest_asyncio.fixture
async def stored_deal(session_maker, seed_carrier, seed_sender):
    """A deal in transit whose agreement carries a storage tariff.

    Written straight into the vault rather than negotiated through the API:
    what is under test is the counter, and a full round of proposals would make
    these tests fail for reasons that have nothing to do with storage.
    """
    from app.models.deal import (
        CardState,
        Deal,
        DealStatus,
        DealVaultMessage,
    )
    from app.models.marketplace import Cargo, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="DXB",
            destination="JFK",
            depart_at=datetime.now(timezone.utc) + timedelta(days=5),
            capacity=8.0,
            allowed_categories=["document"],
            status=TripStatus.open,
            currency="USD",
            storage_terms={
                "free_days": 2,
                "price": 1.0,
                "unit": "kg",
                "currency": "USD",
            },
        )
        db.add(trip)
        await db.flush()
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=100.0,
            currency="USD",
            final_destination=trip.destination,
            weight_kg=3.0,
        )
        db.add(cargo)
        await db.flush()
        deal = Deal(
            cargo_id=cargo.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.in_transit,
        )
        db.add(deal)
        await db.flush()
        db.add(
            DealVaultMessage(
                deal_id=deal.id,
                sender_id=None,
                is_system=True,
                card_kind="terms.agreed",
                card_payload={
                    "price_total": 100.0,
                    "currency": "USD",
                    "payer": "sender",
                    "storage_terms": trip.storage_terms,
                },
                card_state=CardState.accepted,
            )
        )
        await db.commit()
        await db.refresh(deal)
        return deal


async def _card(client, headers, deal_id, kind, payload):
    return await client.post(
        f"/api/deals/{deal_id}/cards",
        headers=headers,
        json={"kind": kind, "payload": payload},
    )


async def test_a_deal_not_in_storage_says_nothing_about_it(
    client, sender_headers, stored_deal
):
    r = await client.get(f"/api/deals/{stored_deal.id}", headers=sender_headers)
    assert r.status_code == 200, r.text
    assert r.json()["storage"] is None


async def test_declaring_storage_starts_the_counter(
    client, carrier_headers, sender_headers, stored_deal
):
    declared = await _card(
        client,
        carrier_headers,
        stored_deal.id,
        "transit.update",
        {"stage": "storage", "tz_offset_minutes": 240},
    )
    assert declared.status_code == 201, declared.text

    r = await client.get(f"/api/deals/{stored_deal.id}", headers=sender_headers)
    state = r.json()["storage"]
    assert state is not None
    # Just declared: nothing has been charged, and the sender can see when it
    # would start to be.
    assert state["paid_days"] == 0
    assert state["free_days"] == 2
    assert state["max_paid_days"] == 14
    assert state["unit"] == "kg"
    assert state["units"] == 3.0
    assert state["charged"] is None


async def test_only_the_carrier_declares_storage(
    client, sender_headers, stored_deal
):
    """The parcel is in the carrier's hands; a sender saying it is in storage
    would be a claim about somebody else's cupboard."""
    r = await _card(
        client,
        sender_headers,
        stored_deal.id,
        "transit.update",
        {"stage": "storage"},
    )
    assert r.status_code == 403, r.text


async def test_the_carrier_bills_and_the_paying_side_answers(
    client, carrier_headers, sender_headers, stored_deal
):
    """Owner, 2026-09-20: «счётчик уведомительный, и сумма за хранение может
    быть изменена». The declared days need not equal the counted ones — and
    because it is money, the other side confirms."""
    await _card(
        client,
        carrier_headers,
        stored_deal.id,
        "transit.update",
        {"stage": "storage", "tz_offset_minutes": 0},
    )
    billed = await _card(
        client,
        carrier_headers,
        stored_deal.id,
        "storage.charged",
        {"days": 3, "amount": 9.0, "currency": "USD"},
    )
    assert billed.status_code == 201, billed.text
    assert billed.json()["requires_ack_by"] == "sender"

    r = await client.get(f"/api/deals/{stored_deal.id}", headers=sender_headers)
    state = r.json()["storage"]
    # The waiting is not over because a bill was written: the counter is still
    # running, and the bill stands beside it.
    assert state is not None
    assert state["charged"]["days"] == 3
    assert state["charged"]["amount"] == 9.0

    ack = await client.post(
        f"/api/deals/{stored_deal.id}/dealvault/messages/{billed.json()['id']}/ack",
        headers=sender_headers,
        json={"decision": "accepted"},
    )
    assert ack.status_code == 200, ack.text


async def test_the_sender_cannot_bill_for_storage(
    client, sender_headers, stored_deal
):
    r = await _card(
        client, sender_headers, stored_deal.id, "storage.charged", {"days": 3}
    )
    assert r.status_code == 403, r.text


async def test_the_handover_ends_the_storage(
    client, carrier_headers, sender_headers, stored_deal
):
    """Nothing is «taken off storage» by hand: the parcel moving on is the end
    of the waiting. A button whose only job is to stop a meter is a button
    people forget, and the meter would then run past the truth."""
    await _card(
        client,
        carrier_headers,
        stored_deal.id,
        "transit.update",
        {"stage": "storage", "tz_offset_minutes": 0},
    )
    handed = await _card(
        client,
        carrier_headers,
        stored_deal.id,
        "delivery.declared",
        {},
    )
    assert handed.status_code == 201, handed.text

    r = await client.get(f"/api/deals/{stored_deal.id}", headers=sender_headers)
    assert r.json()["storage"] is None


async def test_a_trip_without_a_tariff_has_no_counter(
    client, carrier_headers, sender_headers, stored_deal, session_maker
):
    """Silence about storage is not free storage: with no tariff agreed there
    is nothing to count, and the screen says nothing rather than nought."""
    from app.models.deal import DealVaultMessage
    from sqlalchemy import select

    async with session_maker() as db:
        row = (
            await db.execute(
                select(DealVaultMessage).where(
                    DealVaultMessage.deal_id == stored_deal.id,
                    DealVaultMessage.card_kind == "terms.agreed",
                )
            )
        ).scalar_one()
        payload = dict(row.card_payload or {})
        payload.pop("storage_terms", None)
        row.card_payload = payload
        await db.commit()

    await _card(
        client,
        carrier_headers,
        stored_deal.id,
        "transit.update",
        {"stage": "storage"},
    )
    r = await client.get(f"/api/deals/{stored_deal.id}", headers=sender_headers)
    assert r.json()["storage"] is None


# ── the tariff on the trip ────────────────────────────────────────────────


def _trip_body(**over) -> dict:
    return {
        "payment_model": "cash_on_delivery",
        "segments": [
            {
                "origin": "AAA",
                "destination": "BBB",
                "depart_at": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            }
        ],
        "capacity": 3.5,
        "allowed_categories": ["document"],
        **over,
    }


async def test_a_carrier_publishes_a_storage_tariff(client, carrier_headers):
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_trip_body(
            storage_terms={
                "free_days": 2,
                "price": 1.0,
                "unit": "kg",
                "currency": "usd",
            }
        ),
    )
    assert r.status_code == 201, r.text
    # Upper-cased like every other currency on this trip: one spelling, or the
    # listing sorts «usd» and «USD» into two markets.
    assert r.json()["storage_terms"] == {
        "free_days": 2,
        "price": 1.0,
        "unit": "kg",
        "currency": "USD",
    }


async def test_half_a_tariff_is_refused_at_the_trip(client, carrier_headers):
    """A price with no free period, or a free period with no price, is not
    terms a sender could agree to — so it is refused where it is typed rather
    than stored to confuse somebody later."""
    r = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json=_trip_body(storage_terms={"free_days": 2, "unit": "kg"}),
    )
    assert r.status_code == 422, r.text


async def test_a_trip_may_say_nothing_about_storage(client, carrier_headers):
    """Silence stays silence: `None`, not a tariff of nought."""
    r = await client.post("/api/trips", headers=carrier_headers, json=_trip_body())
    assert r.status_code == 201, r.text
    assert r.json()["storage_terms"] is None
