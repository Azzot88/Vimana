"""T3.12.09 — deleting an arbiter who is holding or was offered a dispute.

The dispute belongs to two other people and stays; what goes is this account's
reference to it. Before 2026-09-15 the admin cascade cleared neither, so the
delete failed on the foreign key — and with the pool, an account can be pointed
at a dispute it never answered, which made a stuck row easy to create.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _account(client, prefix: str) -> dict:
    email = unique_email(prefix)
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Arb"})
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = uuid.UUID((await client.get("/api/auth/me", headers=headers)).json()["id"])
    return {"id": me, "headers": headers, "email": email}


async def _superuser(client, session_maker) -> dict:
    from sqlalchemy import select

    from app.models.user import User

    who = await _account(client, "del-admin")
    async with session_maker() as db:
        u = (await db.execute(select(User).where(User.id == who["id"]))).scalar_one()
        u.roles = ["superuser"]
        await db.commit()
    token = await client.post(
        "/api/auth/login", json={"login": who["email"], "password": SEED_PASSWORD}
    )
    who["headers"] = {"Authorization": f"Bearer {token.json()['access_token']}"}
    return who


async def _dispute_on_somebody_elses_deal(session_maker, seed_sender, seed_carrier):
    from app.models.deal import Deal, DealStatus, Dispute, DisputeStatus
    from app.models.marketplace import Cargo, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="DEL",
            destination="ARB",
            depart_at=datetime.now(timezone.utc) + timedelta(days=4),
            capacity=2.0,
            allowed_categories=["document"],
            status=TripStatus.open,
            currency="USD",
        )
        db.add(trip)
        await db.flush()
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=50.0,
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
            status=DealStatus.disputed,
        )
        db.add(deal)
        await db.flush()
        dispute = Dispute(
            deal_id=deal.id,
            opened_by=seed_sender.id,
            reason="other",
            status=DisputeStatus.open,
        )
        db.add(dispute)
        await db.commit()
        return dispute.id


async def test_deleting_an_offered_arbiter_leaves_the_dispute(
    client, session_maker, seed_sender, seed_carrier
):
    from app.models.deal import Dispute
    from app.models.user import User

    admin = await _superuser(client, session_maker)
    arbiter = await _account(client, "del-arb")
    dispute_id = await _dispute_on_somebody_elses_deal(
        session_maker, seed_sender, seed_carrier
    )
    async with session_maker() as db:
        row = await db.get(Dispute, dispute_id)
        row.offered_to_id = arbiter["id"]
        row.offered_at = datetime.now(timezone.utc)
        await db.commit()

    r = await client.delete(f"/api/admin/users/{arbiter['id']}", headers=admin["headers"])
    assert r.status_code == 204, r.text

    async with session_maker() as db:
        assert (await db.get(User, arbiter["id"])) is None
        row = await db.get(Dispute, dispute_id)
        # The quarrel is not theirs to take with them.
        assert row is not None
        assert row.offered_to_id is None
        assert row.offered_at is None


async def test_deleting_the_arbiter_who_claimed_it_leaves_the_dispute(
    client, session_maker, seed_sender, seed_carrier
):
    from app.models.deal import Dispute, DisputeStatus
    from app.models.user import User

    admin = await _superuser(client, session_maker)
    arbiter = await _account(client, "del-arb2")
    dispute_id = await _dispute_on_somebody_elses_deal(
        session_maker, seed_sender, seed_carrier
    )
    async with session_maker() as db:
        row = await db.get(Dispute, dispute_id)
        row.arbiter_id = arbiter["id"]
        row.status = DisputeStatus.claimed
        await db.commit()

    r = await client.delete(f"/api/admin/users/{arbiter['id']}", headers=admin["headers"])
    assert r.status_code == 204, r.text

    async with session_maker() as db:
        assert (await db.get(User, arbiter["id"])) is None
        row = await db.get(Dispute, dispute_id)
        assert row is not None and row.arbiter_id is None
