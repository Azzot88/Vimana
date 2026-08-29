"""T3.42 — offering, accepting and withdrawing a role, with the journal as truth.

The one rule this module exists to hold: **`users.roles` is written here and
nowhere else, and every write appends a `RoleGrant` row in the same
transaction.** Where a role came from stops being answerable the moment that
pairing is broken somewhere else in the codebase. (`core/superuser.py` is the
single exception, and it says why in place: User Zero's role is not granted by
anybody.)

**Roles add up.** `accept` appends and `revoke` removes one element — neither
replaces the list. The column was a single string until T3.42, which made every
grant a silent revocation of the previous one: somebody who arbitrates disputes
*and* drafts corridor rules would have lost the first job on taking the second,
and nothing in the interface or the journal would have said so.

An offer deliberately changes nothing. `users.roles` stays whatever it was until
`accept`, so the permission layer needs no notion of "pending" at all — an
unaccepted offer is invisible to `perms_of` because there is nothing for it to
find. That is what makes the acceptance criterion checkable from outside: call
an arbiter endpoint while an offer is open and get 403, the same as any account.

Functions (PROJECT §6.2a):
- `state_of(db, subject_id, role)` — latest event for the pair, or None.
  Called by: `offer`, `accept`, `decline`, `revoke`, `api/roles`.
- `offer(db, subject, role, actor, reason)` — write an `offered` row.
  Called by: `api/roles.offer_role`.
- `accept(db, subject, role)` / `decline(db, subject, role)` — the subject's
  answer. Called by: `api/roles.accept_offer`, `api/roles.decline_offer`.
- `revoke(db, subject, role, actor, reason)` — take back a live role or an
  unanswered offer. Called by: `api/roles.revoke_role`.
- `pending_offers(db, subject_id)` — roles awaiting this account's answer.
  Called by: `api/roles.my_offers`.
- `journal(db, subject_id)` — the whole history, newest first.
  Called by: `api/roles.role_journal`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import OFFERABLE_ROLES, Role
from app.models.role_grant import RoleGrant, RoleGrantEvent
from app.models.user import User


class RoleError(ValueError):
    """The transition asked for is not available from the current state."""


async def state_of(
    db: AsyncSession, subject_id: uuid.UUID, role: str
) -> RoleGrantEvent | None:
    """The latest event for this pair, or None if the role was never touched."""
    row = (
        await db.execute(
            select(RoleGrant)
            .where(RoleGrant.subject_id == subject_id, RoleGrant.role == role)
            .order_by(desc(RoleGrant.created_at), desc(RoleGrant.id))
            .limit(1)
        )
    ).scalar_one_or_none()
    return row.event if row else None


def _check_offerable(role: str) -> None:
    if role not in OFFERABLE_ROLES:
        raise RoleError(f"`{role}` is not a role that can be offered")


async def offer(
    db: AsyncSession,
    subject: User,
    role: str,
    actor: User,
    reason: str = "",
) -> RoleGrant:
    """Propose a role. Grants nothing until the subject answers."""
    _check_offerable(role)
    if Role.SUPERUSER.value in (subject.roles or []):
        raise RoleError("A superuser already holds every power")
    if subject.id == actor.id:
        # Not paranoia about privilege escalation — the offerer is already a
        # superuser and holds everything. It is that a journal where somebody
        # offered themselves a role records consent that never happened.
        raise RoleError("A role cannot be offered to yourself")

    current = await state_of(db, subject.id, role)
    if current is RoleGrantEvent.offered:
        raise RoleError("This role is already offered and awaiting an answer")
    if current is RoleGrantEvent.accepted:
        raise RoleError("This account already holds the role")

    grant = RoleGrant(
        subject_id=subject.id,
        role=role,
        event=RoleGrantEvent.offered,
        actor_id=actor.id,
        reason=reason,
    )
    db.add(grant)
    return grant


async def accept(db: AsyncSession, subject: User, role: str) -> RoleGrant:
    """The subject says yes. This is the only place a role starts applying."""
    if await state_of(db, subject.id, role) is not RoleGrantEvent.offered:
        raise RoleError("There is no open offer of this role")

    grant = RoleGrant(
        subject_id=subject.id,
        role=role,
        event=RoleGrantEvent.accepted,
        # No actor: the subject is the actor, and storing them twice invites
        # the two columns to disagree.
        reason="",
    )
    db.add(grant)
    # Append, never replace. A new list rather than `.append()`: SQLAlchemy
    # tracks a plain Python list by identity, so mutating it in place leaves the
    # attribute unchanged as far as the session is concerned and the UPDATE is
    # never emitted. The grant would be journalled and the role would not exist.
    if role not in (subject.roles or []):
        subject.roles = [*(subject.roles or []), role]
    return grant


async def decline(db: AsyncSession, subject: User, role: str) -> RoleGrant:
    """The subject says no. `users.roles` is not touched — it never changed."""
    if await state_of(db, subject.id, role) is not RoleGrantEvent.offered:
        raise RoleError("There is no open offer of this role")

    grant = RoleGrant(
        subject_id=subject.id, role=role, event=RoleGrantEvent.declined, reason=""
    )
    db.add(grant)
    return grant


async def revoke(
    db: AsyncSession, subject: User, role: str, actor: User, reason: str = ""
) -> RoleGrant:
    """Take back a live role, or an offer nobody answered.

    Both are one event on purpose: the row before it already says which case
    this was, and a fifth event name would be a second description of the same
    fact, to be kept in sync by hand.
    """
    current = await state_of(db, subject.id, role)
    if current not in (RoleGrantEvent.offered, RoleGrantEvent.accepted):
        raise RoleError("This account neither holds nor has been offered the role")

    grant = RoleGrant(
        subject_id=subject.id,
        role=role,
        event=RoleGrantEvent.revoked,
        actor_id=actor.id,
        reason=reason,
    )
    db.add(grant)
    # Only a role that had actually started applying comes off the list, and
    # only that one element: withdrawing an unanswered offer must leave the
    # other roles alone, and so must revoking a live one.
    if current is RoleGrantEvent.accepted:
        subject.roles = [r for r in (subject.roles or []) if r != role]
    return grant


async def pending_offers(db: AsyncSession, subject_id: uuid.UUID) -> list[RoleGrant]:
    """Offers this account has not answered yet, newest first."""
    rows = (
        await db.execute(
            select(RoleGrant)
            .where(RoleGrant.subject_id == subject_id)
            .order_by(desc(RoleGrant.created_at), desc(RoleGrant.id))
        )
    ).scalars().all()

    seen: set[str] = set()
    out: list[RoleGrant] = []
    for row in rows:
        if row.role in seen:
            continue
        seen.add(row.role)
        if row.event is RoleGrantEvent.offered:
            out.append(row)
    return out


async def journal(db: AsyncSession, subject_id: uuid.UUID) -> list[RoleGrant]:
    """Every event for this account, newest first."""
    return list(
        (
            await db.execute(
                select(RoleGrant)
                .where(RoleGrant.subject_id == subject_id)
                .order_by(desc(RoleGrant.created_at), desc(RoleGrant.id))
            )
        ).scalars().all()
    )
