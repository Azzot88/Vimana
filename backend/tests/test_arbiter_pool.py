"""T3.12.09 — the arbiter pool and random assignment.

Owner, 2026-09-14: the pool is the default; the platform offers a dispute to a
random arbiter among the least loaded; they accept or decline; a refusal or 24
hours of silence pass it on, and whoever passed is not asked again. A party of
the deal is never a candidate.

Choices are made from an explicit `pool` of this file's own arbiters: the test
database is never reset and holds every arbiter any test ever made.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _arbiter(client, session_maker, prefix: str) -> dict:
    from app.models.user import User

    email = unique_email(prefix)
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Arb"})
    login = await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = uuid.UUID((await client.get("/api/auth/me", headers=headers)).json()["id"])
    async with session_maker() as db:
        (await db.get(User, me)).roles = ["arbiter"]
        await db.commit()
    return {"id": me, "headers": headers}


async def _deal(session_maker, seed_sender, seed_carrier, **deal_fields):
    from app.models.deal import Deal, DealStatus
    from app.models.marketplace import Cargo, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="POL",
            destination="ARB",
            depart_at=datetime.now(timezone.utc) + timedelta(days=9),
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
            final_destination="ARB",
            weight_kg=1.0,
        )
        db.add(cargo)
        await db.flush()
        deal = Deal(
            cargo_id=cargo.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.in_transit,
            **deal_fields,
        )
        db.add(deal)
        await db.commit()
        return deal.id


async def _dispute(session_maker, seed_sender, seed_carrier, *, deal_fields=None, **fields):
    """A dispute written directly — no offer is made, so nothing random happens
    before the test chooses."""
    from app.models.deal import Dispute, DisputeStatus

    deal_id = await _deal(session_maker, seed_sender, seed_carrier, **(deal_fields or {}))
    async with session_maker() as db:
        dispute = Dispute(
            deal_id=deal_id,
            opened_by=seed_sender.id,
            reason="other",
            status=fields.pop("status", DisputeStatus.open),
            **fields,
        )
        db.add(dispute)
        await db.commit()
        return dispute.id


async def _set_param(session_maker, key: str, value: str, value_type) -> None:
    from app.models.platform_params import GLOBAL_SCOPE, PlatformParameter

    async with session_maker() as db:
        db.add(
            PlatformParameter(
                key=key,
                scope=GLOBAL_SCOPE,
                value=value,
                value_type=value_type,
                effective_from=datetime.now(timezone.utc),
                comment="test_arbiter_pool",
            )
        )
        await db.commit()


async def _offer(session_maker, dispute_id, pool):
    from app.core.arbitration import offer_next
    from app.models.deal import Dispute

    async with session_maker() as db:
        dispute = await db.get(Dispute, dispute_id)
        chosen = await offer_next(db, dispute, pool=pool)
        await db.commit()
        return chosen


async def _row(session_maker, dispute_id):
    from app.models.deal import Dispute

    async with session_maker() as db:
        return await db.get(Dispute, dispute_id)


async def test_a_party_is_never_offered_the_dispute(
    client, session_maker, seed_sender, seed_carrier
):
    """`§3.12.6` п. 3 — excluded in the query, not refused afterwards."""
    a = await _arbiter(client, session_maker, "pool-party")
    b = await _arbiter(client, session_maker, "pool-free")
    dispute_id = await _dispute(
        session_maker, seed_sender, seed_carrier, deal_fields={"recipient_id": a["id"]}
    )
    for _ in range(8):
        assert await _offer(session_maker, dispute_id, [a["id"], b["id"]]) in (b["id"],)
        # Put it back so every round chooses from the same two.
        async with session_maker() as db:
            from app.models.deal import Dispute

            row = await db.get(Dispute, dispute_id)
            row.offered_to_id = None
            row.passed_over = []
            await db.commit()


async def test_the_least_loaded_arbiter_is_offered(
    client, session_maker, seed_sender, seed_carrier
):
    from app.models.deal import DisputeStatus

    busy = await _arbiter(client, session_maker, "pool-busy")
    idle = await _arbiter(client, session_maker, "pool-idle")
    await _dispute(
        session_maker, seed_sender, seed_carrier,
        arbiter_id=busy["id"], status=DisputeStatus.claimed,
    )
    dispute_id = await _dispute(session_maker, seed_sender, seed_carrier)

    assert await _offer(session_maker, dispute_id, [busy["id"], idle["id"]]) == idle["id"]


async def test_nobody_under_the_cap_means_no_offer(
    client, session_maker, seed_sender, seed_carrier
):
    from app.models.deal import DisputeStatus
    from app.models.platform_params import ParamValueType

    busy = await _arbiter(client, session_maker, "pool-cap")
    await _dispute(
        session_maker, seed_sender, seed_carrier,
        arbiter_id=busy["id"], status=DisputeStatus.claimed,
    )
    dispute_id = await _dispute(session_maker, seed_sender, seed_carrier)
    await _set_param(session_maker, "arbiter_max_open_disputes", "1", ParamValueType.integer)
    try:
        assert await _offer(session_maker, dispute_id, [busy["id"]]) is None
        assert (await _row(session_maker, dispute_id)).offered_to_id is None
    finally:
        await _set_param(session_maker, "arbiter_max_open_disputes", "5", ParamValueType.integer)


async def test_only_the_offered_arbiter_accepts(
    client, session_maker, seed_sender, seed_carrier
):
    offered = await _arbiter(client, session_maker, "pool-yes")
    other = await _arbiter(client, session_maker, "pool-other")
    dispute_id = await _dispute(session_maker, seed_sender, seed_carrier)
    assert await _offer(session_maker, dispute_id, [offered["id"]]) == offered["id"]

    refused = await client.post(f"/api/disputes/{dispute_id}/accept", headers=other["headers"])
    assert refused.status_code == 403, refused.text

    r = await client.post(f"/api/disputes/{dispute_id}/accept", headers=offered["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "claimed"
    assert body["arbiter_id"] == str(offered["id"])
    assert body["offered_to_id"] is None


async def test_declining_passes_it_on_for_good(
    client, session_maker, seed_sender, seed_carrier
):
    first = await _arbiter(client, session_maker, "pool-no")
    dispute_id = await _dispute(session_maker, seed_sender, seed_carrier)
    await _offer(session_maker, dispute_id, [first["id"]])

    r = await client.post(f"/api/disputes/{dispute_id}/decline", headers=first["headers"])
    assert r.status_code == 200, r.text
    row = await _row(session_maker, dispute_id)
    assert str(first["id"]) in row.passed_over
    assert row.offered_to_id != first["id"]

    # Asked again? Never: whoever passed is out of this dispute's candidates.
    assert await _offer(session_maker, dispute_id, [first["id"]]) is None


async def test_silence_passes_it_on(client, session_maker, seed_sender, seed_carrier):
    from app.models.deal import Dispute
    from app.tasks.cleanup import _reassign_arbiters

    silent = await _arbiter(client, session_maker, "pool-silent")
    next_one = await _arbiter(client, session_maker, "pool-next")
    dispute_id = await _dispute(session_maker, seed_sender, seed_carrier)
    await _offer(session_maker, dispute_id, [silent["id"]])

    # An offer made an hour ago is left alone.
    swept = await _reassign_arbiters(50, dispute_ids=[dispute_id], pool=[silent["id"], next_one["id"]])
    assert swept == {"moved": 0, "offered": 0}

    async with session_maker() as db:
        row = await db.get(Dispute, dispute_id)
        row.offered_at = datetime.now(timezone.utc) - timedelta(hours=25)
        await db.commit()
    swept = await _reassign_arbiters(50, dispute_ids=[dispute_id], pool=[silent["id"], next_one["id"]])
    assert swept == {"moved": 1, "offered": 1}
    row = await _row(session_maker, dispute_id)
    assert row.offered_to_id == next_one["id"]
    assert row.passed_over == [str(silent["id"])]


async def test_opening_a_dispute_offers_it_to_the_pool(
    client, session_maker, sender_headers, seed_sender, seed_carrier
):
    await _arbiter(client, session_maker, "pool-open")
    deal_id = await _deal(session_maker, seed_sender, seed_carrier)
    r = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "other", "details": "pool"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["offered_to_id"] is not None
    assert r.json()["offered_to_id"] not in (str(seed_sender.id), str(seed_carrier.id))


async def test_the_chosen_arbiter_is_told_by_letter(
    client, session_maker, monkeypatch, sender_headers, seed_sender, seed_carrier
):
    """Without the letter the offer lived only inside the queue screen, and the
    24-hour handoff ran against somebody who was never told."""
    from app.models.deal import Dispute
    from app.tasks import notifications

    sent: list[tuple] = []
    monkeypatch.setattr(
        notifications.send_dispute_offered, "delay", lambda *args: sent.append(args)
    )

    await _arbiter(client, session_maker, "pool-letter")
    deal_id = await _deal(session_maker, seed_sender, seed_carrier)
    r = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "other", "details": "letter"},
    )
    assert r.status_code == 201, r.text

    async with session_maker() as db:
        row = await db.get(Dispute, uuid.UUID(r.json()["id"]))
        assert row.offered_to_id is not None
        assert sent and sent[0][0] == str(row.offered_to_id)


async def test_the_common_queue_is_closed_in_the_pool(
    client, session_maker, seed_sender, seed_carrier
):
    arbiter = await _arbiter(client, session_maker, "pool-claim")
    dispute_id = await _dispute(session_maker, seed_sender, seed_carrier)
    r = await client.post(f"/api/disputes/{dispute_id}/claim", headers=arbiter["headers"])
    assert r.status_code == 409, r.text


async def test_requests_mode_lets_arbiters_take_what_is_not_theirs(
    client, session_maker, seed_sender, seed_carrier
):
    from app.models.platform_params import ParamValueType

    taker = await _arbiter(client, session_maker, "req-take")
    party = await _arbiter(client, session_maker, "req-party")
    dispute_id = await _dispute(
        session_maker, seed_sender, seed_carrier, deal_fields={"recipient_id": party["id"]}
    )
    await _set_param(session_maker, "arbiter_assignment_mode", "requests", ParamValueType.string)
    try:
        listed = await client.get("/api/admin/disputes?limit=100", headers=taker["headers"])
        mine = [d for d in listed.json()["items"] if d["id"] == str(dispute_id)]
        assert mine and mine[0]["claimable"] is True

        hidden = await client.get("/api/admin/disputes?limit=100", headers=party["headers"])
        assert str(dispute_id) not in [d["id"] for d in hidden.json()["items"]]

        r = await client.post(f"/api/disputes/{dispute_id}/claim", headers=taker["headers"])
        assert r.status_code == 200, r.text
    finally:
        await _set_param(session_maker, "arbiter_assignment_mode", "pool", ParamValueType.string)
