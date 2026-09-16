"""ЭТАП 3.12 — the data moves inside migrations, run against rows built here.

`conftest` builds the test database with `create_all` and then applies each
migration's `UPGRADE`, so the `BACKFILL` and `MOVE` halves never ran in a test:
there was nothing to move in a database that was created empty. Those halves are
the part that cannot be re-run if it is wrong — by the time anybody notices, the
rows they were meant to fix have been read as correct for a week.

Each test builds the «before» shape itself and runs the statements straight from
the migration file (`_migration_statements(..., "BACKFILL")`), so the SQL under
test is the SQL that shipped. `vimana_test` is never reset, so each test cleans
up what it made.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from tests.conftest import SEED_PASSWORD, _migration_statements, make_account, unique_email


async def test_0093_fills_a_cargo_from_the_terms_of_its_deal(
    session_maker, seed_sender, seed_carrier
):
    """T3.12.04 moved the cargo out of the terms; `0093` had to carry the old
    deals across. A cargo written before the columns existed takes its weight,
    size, fragility and link from the terms card of its own deal — the agreed
    one where there is one."""
    from app.models.deal import Deal, DealStatus, DealVaultMessage
    from app.models.marketplace import Cargo, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="MIG",
            destination="RAT",
            depart_at=datetime.now(timezone.utc) + timedelta(days=6),
            capacity=3.0,
            allowed_categories=["document"],
            status=TripStatus.open,
            currency="USD",
        )
        db.add(trip)
        await db.flush()
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=80.0,
            currency="USD",
            final_destination="RAT",
            # The «before» shape: everything the terms used to carry is empty.
            weight_kg=None,
            dimensions_cm=None,
            fragile=False,
            open_on_handover=False,
            cargo_url=None,
        )
        db.add(cargo)
        await db.flush()
        deal = Deal(
            cargo_id=cargo.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.accepted,
        )
        db.add(deal)
        await db.flush()
        db.add(
            DealVaultMessage(
                deal_id=deal.id,
                is_system=True,
                card_kind="terms.agreed",
                card_payload={
                    "weight_kg": 2.5,
                    "dimensions_cm": [10, 20, 30],
                    "cargo_fragile": True,
                    "cargo_open_on_handover": True,
                    "cargo_url": "https://example.test/item",
                    "cargo_what": "a box of papers",
                },
            )
        )
        await db.commit()
        cargo_id = cargo.id

    async with session_maker() as db:
        for statement in _migration_statements("0093_cargo_out_of_terms.py", "BACKFILL"):
            await db.execute(text(statement))
        await db.commit()

    async with session_maker() as db:
        moved = await db.get(Cargo, cargo_id)
        assert moved.weight_kg == 2.5
        assert moved.dimensions_cm == [10, 20, 30]
        assert moved.fragile is True
        assert moved.open_on_handover is True
        assert moved.cargo_url == "https://example.test/item"
        assert moved.description == "a box of papers"


async def test_0095_moves_close_marks_into_pairs(client, session_maker):
    """T3.12.06 replaced the `close` tier with a pair somebody asks for. The
    move is the only thing standing between the old marks and silence: mutual
    marks become an accepted pair, a one-sided one becomes a request.

    The column is put back for the test and dropped again — `0095` itself drops
    it, and the test database has already been through that.
    """
    people = []
    for prefix in ("mig-close-a", "mig-close-b", "mig-close-c"):
        email = unique_email(prefix)
        await make_account(
            {"email": email, "password": SEED_PASSWORD, "display_name": "Mig"}
        )
        login = await client.post(
            "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = (await client.get("/api/auth/me", headers=headers)).json()["id"]
        people.append(uuid.UUID(me))
    a, b, c = people

    async with session_maker() as db:
        await db.execute(
            text(
                "ALTER TABLE connections ADD COLUMN IF NOT EXISTS tier "
                "VARCHAR(16) NOT NULL DEFAULT 'connection'"
            )
        )
        for one, two, tier in ((a, b, "close"), (b, a, "close"), (a, c, "close")):
            await db.execute(
                text(
                    "INSERT INTO connections (id, user_id, connected_user_id, tier, created_at) "
                    "VALUES (gen_random_uuid(), :u, :v, :t, now())"
                ),
                {"u": str(one), "v": str(two), "t": tier},
            )
        await db.commit()

    try:
        async with session_maker() as db:
            # Everything but the `ALTER TABLE ... DROP COLUMN tier` that ends the
            # list: the column is dropped in the cleanup below either way.
            for statement in _migration_statements("0095_close_pairs.py", "MOVE"):
                if "DROP COLUMN" in statement:
                    continue
                await db.execute(text(statement))
            await db.commit()

        from sqlalchemy import or_, select

        from app.models.social import ClosePair

        async with session_maker() as db:
            pairs = (
                (
                    await db.execute(
                        select(ClosePair).where(
                            or_(
                                ClosePair.requester_id.in_(people),
                                ClosePair.addressee_id.in_(people),
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_pair = {frozenset((p.requester_id, p.addressee_id)): p for p in pairs}
            assert len(by_pair) == 2

            mutual = by_pair[frozenset((a, b))]
            assert mutual.accepted_at is not None, "both said close — an accepted pair"

            one_sided = by_pair[frozenset((a, c))]
            assert one_sided.requester_id == a
            assert one_sided.accepted_at is None, "one said close — a request"
    finally:
        async with session_maker() as db:
            await db.execute(
                text(
                    "DELETE FROM close_pairs WHERE requester_id = ANY(:ids) "
                    "OR addressee_id = ANY(:ids)"
                ),
                {"ids": [str(p) for p in people]},
            )
            await db.execute(
                text(
                    "DELETE FROM connections WHERE user_id = ANY(:ids) "
                    "OR connected_user_id = ANY(:ids)"
                ),
                {"ids": [str(p) for p in people]},
            )
            await db.execute(text("ALTER TABLE connections DROP COLUMN IF EXISTS tier"))
            await db.commit()
