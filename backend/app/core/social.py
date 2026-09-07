"""T3.11.24 — contacts, and what «close» is allowed to mean.

Owner's definition, 2026-09-07:

- **Contacts (`Connection`)** — acquaintances. Somebody who carried something
  once, or who is interesting on a corridor. **May be one-way**: keeping a
  carrier in your list says nothing about whether they keep you in theirs.
- **Close (`close`)** — the people you trust: family, and whoever would cover
  you financially. **Two-way only.** They see the whole profile, addresses
  included; the seeing part comes later, the tier and the rule are set now.

The row in `connections` is directed — `user_id` keeps `connected_user_id` — so
the tier on it is one half of a statement. This module owns the other half:
`closeness` is the only place that reads both rows, and everything else asks it
rather than a single row, because a single row cannot know.

Functions (PROJECT §6.2a):
- `pair_state(mine, theirs)` — the rule itself, over two tiers.
  Called by: `closeness`, `api.social.list_connections`.
- `closeness(db, a, b)` — the state between two people, from a's side.
  Called by: `api.social.set_tier`, `pair_state`'s tests.
- `add_connection(db, user_id, other_id)` — one directed row, idempotent.
  Called by: `api.social.add_connection`.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import Connection

TIERS = ("connection", "close")

#: What `closeness` can answer. `close_pending` is the honest name for «I said
#: close and they have not»: the tier is stored, and it does not yet mean
#: anything about the pair. Rendering it as `close` would let one person decide
#: they are trusted by another.
STATES = ("none", "connection", "close_pending", "close")


def pair_state(mine: str | None, theirs: str | None) -> str:
    """The rule, over the two tiers — no database, so it can be reused.

    The list endpoint reads everyone's other half in one query and calls this
    per row; `closeness` reads one pair and calls the same thing. Writing the
    comparison twice is how the two would drift, and the direction they drift in
    is «close» meaning different things in a list and on a profile.
    """
    if mine is None:
        return "none"
    if mine == "close" and theirs == "close":
        return "close"
    if mine == "close":
        return "close_pending"
    return "connection"


async def closeness(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> str:
    """How close `a` and `b` are, read from both directed rows."""
    rows = dict(
        (
            await db.execute(
                select(Connection.user_id, Connection.tier).where(
                    Connection.user_id.in_([a, b]),
                    Connection.connected_user_id.in_([a, b]),
                )
            )
        ).all()
    )
    return pair_state(rows.get(a), rows.get(b))


async def add_connection(
    db: AsyncSession, user_id: uuid.UUID, other_id: uuid.UUID
) -> Connection:
    """Add `other_id` to `user_id`'s contacts. One row, one direction.

    Idempotent, including under a race: the unique index is what decides, and
    the loser re-reads because the row it wanted exists — which was the whole
    question. Nothing is written the other way: a contact list is a statement
    about whom *you* keep, and writing into someone else's would let anyone
    populate a stranger's list.
    """
    existing = (
        await db.execute(
            select(Connection).where(
                Connection.user_id == user_id,
                Connection.connected_user_id == other_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = Connection(user_id=user_id, connected_user_id=other_id)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        row = (
            await db.execute(
                select(Connection).where(
                    Connection.user_id == user_id,
                    Connection.connected_user_id == other_id,
                )
            )
        ).scalar_one()
    return row
