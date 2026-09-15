"""T3.11.24 / T3.12.06 — contacts, and closeness as a thing of its own.

Owner's definition, 2026-09-07:

- **Contacts (`Connection`)** — acquaintances. Somebody who carried something
  once, or who is interesting on a corridor. **May be one-way**: keeping a
  carrier in your list says nothing about whether they keep you in theirs.
- **Close** — the people you trust: family, and whoever would cover you
  financially. **Two-way only.**

T3.12.06 (owner, 2026-09-14): closeness is **asked and accepted** — a
`ClosePair` row, asked only of somebody in the asker's contacts, ended by either
side. It used to be a `tier` on each directed contact row with the pair close
when both happened to say so; this module is still the one place that turns the
record into an answer, now from one table instead of two halves.

Functions (PROJECT §6.2a):
- `state_of(pair, me)` — `close` · `close_pending` (I asked) · `close_requested`
  (asked of me) · `none`. Called by: `closeness`, `close_states`,
  `api.social._close_out`.
- `open_pair(db, a, b)` — the pending or accepted pair between two people.
  Called by: `closeness`, `api.social.request_close`, `api.social.end_close`.
- `open_pairs(db, me)` — every open pair I am in. Called by: `api.social.list_close`.
- `closeness(db, a, b)` — the state from a's side, as a contact row reads it.
  Called by: `api.social.add_connection`.
- `close_states(db, me, others)` — the same for many people, one query.
  Called by: `api.social.list_connections`.
- `add_connection(db, user_id, other_id)` — one directed row, idempotent.
  Called by: `api.social.add_connection`.
"""
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import ClosePair, Connection

STATES = ("none", "close_pending", "close_requested", "close")

#: A pair that has not been declined or ended — pending or accepted.
_OPEN = (ClosePair.declined_at.is_(None), ClosePair.ended_at.is_(None))


def _between(a: uuid.UUID, b: uuid.UUID):
    return or_(
        and_(ClosePair.requester_id == a, ClosePair.addressee_id == b),
        and_(ClosePair.requester_id == b, ClosePair.addressee_id == a),
    )


def state_of(pair: ClosePair | None, me: uuid.UUID) -> str:
    """The rule, over one row. `close_pending` is the honest name for «I asked
    and they have not answered»: rendering it as `close` would let one person
    decide they are trusted by another."""
    if pair is None or pair.declined_at is not None or pair.ended_at is not None:
        return "none"
    if pair.accepted_at is not None:
        return "close"
    return "close_pending" if pair.requester_id == me else "close_requested"


async def open_pair(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> ClosePair | None:
    # At most one, by `uq_close_pairs_open`.
    return (
        await db.execute(select(ClosePair).where(_between(a, b), *_OPEN))
    ).scalar_one_or_none()


async def open_pairs(db: AsyncSession, me: uuid.UUID) -> list[ClosePair]:
    return list(
        (
            await db.execute(
                select(ClosePair)
                .where(
                    or_(ClosePair.requester_id == me, ClosePair.addressee_id == me),
                    *_OPEN,
                )
                .order_by(ClosePair.requested_at.desc())
            )
        ).scalars().all()
    )


async def closeness(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> str:
    """How close `a` and `b` are, from a's side; a contact with nothing asked
    reads `connection`."""
    state = state_of(await open_pair(db, a, b), a)
    return "connection" if state == "none" else state


async def is_close(db: AsyncSession, a: uuid.UUID | None, b: uuid.UUID) -> bool:
    """T3.12.06 pt.2 — are these two people close, as an accepted pair?

    `a` may be None (an anonymous viewer) and may be `b` (looking at oneself):
    neither is closeness. Called by: `api.trust.public_identity`,
    `api.trust.user_trust_metrics`, `api.uba.get_user_uba`.
    """
    if a is None or a == b:
        return False
    return state_of(await open_pair(db, a, b), a) == "close"


async def close_states(
    db: AsyncSession, me: uuid.UUID, others: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """`closeness` for a whole contact list in one query. People with nothing
    open are left out — the caller's default is theirs to choose."""
    if not others:
        return {}
    pairs = (
        await db.execute(
            select(ClosePair).where(
                or_(
                    and_(ClosePair.requester_id == me, ClosePair.addressee_id.in_(others)),
                    and_(ClosePair.addressee_id == me, ClosePair.requester_id.in_(others)),
                ),
                *_OPEN,
            )
        )
    ).scalars().all()
    return {
        (p.addressee_id if p.requester_id == me else p.requester_id): state_of(p, me)
        for p in pairs
    }


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
