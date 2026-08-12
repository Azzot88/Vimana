"""T_TEST.6 — accounts and trips for a load run, created the way the product does.

    docker compose exec -T backend python -m app.cli.load_seed --password '<secret>'
    docker compose exec -T backend python -m app.cli.load_seed --password '<secret>' --accounts 4 --trips 60
    docker compose exec -T backend python -m app.cli.load_seed --purge

**Why this exists.** Three of the four k6 scenarios died on 2026-08-10, when
`POST /auth/register` was removed in `T3.28 pt.3b`: an account is now born from a
code sent to a mailbox, and k6 cannot read a mailbox. Everything the load suite
knows about the product has been read-only since — the write path, and with it
the one deliberate serialisation point in the product (`pg_advisory_xact_lock`
per deal), has never been measured at all.

**Seeded accounts, not a test-only endpoint.** The obvious alternative is a
door that mints a session for a load run. An endpoint that mints sessions is an
endpoint that mints sessions, whatever the comment above it says, and it would
live in production forever for the sake of a test that runs monthly. Password
sign-in still exists; accounts that already have a password need no door.

**The password is an argument with no default.** A credential committed to a
repository is a credential, and these are real accounts on a real deployment.
The operator picks it and gives the same value to k6 as `K6_PASSWORD`.

**The `@e2e.vimana.local` convention does the cleaning.** The TLD is
unresolvable, so nothing is ever mailed, and `cleanup_e2e_users` (daily) prunes
these accounts and everything cascading off them after 24 h. That task is the
only reason repeated seeding is safe; `--purge` is for when you want them gone
now rather than tomorrow.

Functions (PROJECT §6.2a):
- `main(argv)` — CLI entry. Called by: `python -m app.cli.load_seed`.
- `seed(db, count, trips, password)` — create what is missing, skip what is not.
  Called by: `main`.
- `purge(db)` — delete the seeded accounts and their trips. Called by: `main`.
- `email_for(index)` — the deterministic address k6 signs in with, so the
  scenarios need no list. Called by: `seed`, `purge`, `load/lib/config.js` (by
  convention — the pattern is duplicated there and named in both places).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.accounts import create_user
from app.core.database import AsyncSessionLocal
from app.models.marketplace import Trip, TripStatus
from app.models.user import User

#: Same domain the Playwright suite uses. Unresolvable on purpose.
DOMAIN = "e2e.vimana.local"
#: The prefix `cleanup_e2e_users` and `purge` both match on.
PREFIX = "k6-load"

#: Page one is 20 (`core/pagination.DEFAULT_LIMIT`), so anything less than 21
#: leaves `next_cursor` null and the cursor path untested — which is exactly
#: what happened in every run up to 2026-08-11.
DEFAULT_TRIPS = 40
DEFAULT_ACCOUNTS = 4


def email_for(index: int) -> str:
    return f"{PREFIX}-{index}@{DOMAIN}"


async def seed(db, count: int, trips: int, password: str) -> dict:
    """Create the missing accounts and trips. Existing ones are left alone."""
    made_accounts = 0
    users: list[User] = []

    for index in range(count):
        address = email_for(index)
        existing = (
            await db.execute(select(User).where(User.email == address))
        ).scalar_one_or_none()
        if existing is not None:
            users.append(existing)
            continue
        user = await create_user(
            db,
            email=address,
            password=password,
            display_name=f"k6 load {index}",
            can_carry=True,
            can_send=True,
            # Confirmed, because the alternative is a load run that spends its
            # first minute measuring an unverified-account banner. Nothing is
            # mailed to this domain either way.
            verified=True,
        )
        users.append(user)
        made_accounts += 1

    await db.commit()

    carrier = users[0]
    already = (
        await db.execute(
            select(Trip).where(Trip.carrier_id == carrier.id, Trip.status == TripStatus.open)
        )
    ).scalars().all()

    made_trips = 0
    depart = datetime.now(timezone.utc) + timedelta(days=7)
    for index in range(len(already), trips):
        db.add(
            Trip(
                carrier_id=carrier.id,
                # Real corridor codes: the browse scenario filters on DXB↔JFK,
                # and trips nobody's filter matches would leave the filtered
                # queries measuring an empty result.
                origin="DXB" if index % 2 else "JFK",
                destination="JFK" if index % 2 else "DXB",
                depart_at=depart + timedelta(hours=index),
                capacity=10.0,
                allowed_categories=["document"],
                status=TripStatus.open,
            )
        )
        made_trips += 1

    await db.commit()
    return {"accounts": made_accounts, "trips": made_trips, "total_accounts": len(users)}


async def purge(db) -> dict:
    """Remove the seeded accounts and their trips, now rather than tomorrow."""
    ids = (
        await db.execute(
            select(User.id).where(User.email.like(f"{PREFIX}-%@{DOMAIN}"))
        )
    ).scalars().all()
    if not ids:
        return {"accounts": 0, "trips": 0}

    trips = await db.execute(delete(Trip).where(Trip.carrier_id.in_(ids)))
    users = await db.execute(delete(User).where(User.id.in_(ids)))
    await db.commit()
    return {"accounts": users.rowcount or 0, "trips": trips.rowcount or 0}


async def _run(args) -> int:
    async with AsyncSessionLocal() as db:
        if args.purge:
            result = await purge(db)
            print(f"purged: {result['accounts']} accounts, {result['trips']} trips")
            return 0

        if not args.password:
            print(
                "--password is required. It is not defaulted on purpose: these are "
                "real accounts on a real deployment, and a credential in a "
                "repository is a credential. Give k6 the same value as K6_PASSWORD.",
                file=sys.stderr,
            )
            return 2

        result = await seed(db, args.accounts, args.trips, args.password)
        print(
            f"seeded: +{result['accounts']} accounts (total {result['total_accounts']}), "
            f"+{result['trips']} trips"
        )
        print(f"sign in as: {email_for(0)} … {email_for(result['total_accounts'] - 1)}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed accounts and trips for k6 runs.")
    parser.add_argument("--accounts", type=int, default=DEFAULT_ACCOUNTS)
    parser.add_argument("--trips", type=int, default=DEFAULT_TRIPS)
    parser.add_argument("--password", default="")
    parser.add_argument("--purge", action="store_true", help="delete them instead")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
