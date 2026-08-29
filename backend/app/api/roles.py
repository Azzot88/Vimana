"""T3.42 — role offers: the superuser's side and the subject's side.

Two surfaces, deliberately separate. The superuser offers and revokes; the
subject accepts or declines. Nothing here writes `users.role` — that happens in
`core/roles`, which is also where the journal row is appended, so the two cannot
come apart.

Wording follows DESIGNGUIDELINES §9.1: until the answer comes back the API says
`offered`, never `assigned`. The difference is not a nicety — it is checkable
from outside, because an account with an open offer is refused by every
endpoint the role guards.

Endpoints:
- `POST   /api/admin/users/{user_id}/roles`          — offer
- `DELETE /api/admin/users/{user_id}/roles/{role}`   — revoke a role or an offer
- `GET    /api/admin/users/{user_id}/roles`          — the journal for one account
- `GET    /api/me/roles`                             — my role and my open offers
- `POST   /api/me/roles/{role}/accept`
- `POST   /api/me/roles/{role}/decline`
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import roles as roles_core
from app.core.database import get_db
from app.core.permissions import OFFERABLE_ROLES, Permission, require_perm
from app.models.role_grant import RoleGrant, RoleGrantEvent
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


class OfferBody(BaseModel):
    role: str
    reason: str = Field(default="", max_length=2000)


class RevokeBody(BaseModel):
    reason: str = Field(default="", max_length=2000)


class RoleGrantOut(BaseModel):
    id: uuid.UUID
    role: str
    event: RoleGrantEvent
    actor_id: uuid.UUID | None
    actor_name: str | None
    reason: str
    created_at: datetime


class MyRolesOut(BaseModel):
    #: Every role this account actually holds. Empty for an ordinary member.
    roles: list[str]
    #: Roles proposed and not yet answered. An entry here grants nothing.
    offers: list[RoleGrantOut]


class PendingOfferOut(RoleGrantOut):
    """An open offer, with enough about the subject to be actionable.

    The admin list answers "who has been offered what and is not replying".
    Without the subject's name and address that is a page of UUIDs, and the
    person reading it would have to look each one up in another screen.
    """

    subject_id: uuid.UUID
    subject_name: str
    subject_contact: str | None


async def _with_actor_names(
    db: AsyncSession, grants: list[RoleGrant]
) -> list[RoleGrantOut]:
    """Attach the offerer's display name — an id alone is not an answer.

    "Who proposed this" is the question the acceptance screen has to answer, and
    a UUID answers it only for somebody with database access.
    """
    actor_ids = {g.actor_id for g in grants if g.actor_id}
    names: dict[uuid.UUID, str] = {}
    if actor_ids:
        rows = (
            await db.execute(
                select(User.id, User.display_name).where(User.id.in_(actor_ids))
            )
        ).all()
        names = {row[0]: row[1] or "" for row in rows}

    return [
        RoleGrantOut(
            id=g.id,
            role=g.role,
            event=g.event,
            actor_id=g.actor_id,
            actor_name=names.get(g.actor_id) if g.actor_id else None,
            reason=g.reason or "",
            created_at=g.created_at,
        )
        for g in grants
    ]


# ─────────────────────────── superuser side ───────────────────────────

@router.post("/admin/users/{user_id}/roles", response_model=RoleGrantOut, status_code=201)
async def offer_role(
    user_id: uuid.UUID,
    body: OfferBody,
    actor: User = Depends(require_perm(Permission.ROLE_OFFER)),
    db: AsyncSession = Depends(get_db),
):
    subject = await db.get(User, user_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        grant = await roles_core.offer(db, subject, body.role, actor, body.reason)
    except roles_core.RoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(grant)

    # Fire-and-forget, like every other security letter: a broker that is down
    # must not turn an offer into a failed request.
    try:
        from app.tasks.notifications import send_role_offered

        send_role_offered.delay(
            str(subject.id), body.role, actor.display_name or ""
        )
    except Exception:
        logger.exception("could not queue role-offer letter for %s", subject.id)

    return (await _with_actor_names(db, [grant]))[0]


@router.delete("/admin/users/{user_id}/roles/{role}", response_model=RoleGrantOut)
async def revoke_role(
    user_id: uuid.UUID,
    role: str,
    body: RevokeBody | None = None,
    actor: User = Depends(require_perm(Permission.ROLE_OFFER)),
    db: AsyncSession = Depends(get_db),
):
    subject = await db.get(User, user_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        grant = await roles_core.revoke(
            db, subject, role, actor, body.reason if body else ""
        )
    except roles_core.RoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(grant)
    return (await _with_actor_names(db, [grant]))[0]


@router.get("/admin/users/{user_id}/roles", response_model=list[RoleGrantOut])
async def role_journal(
    user_id: uuid.UUID,
    _: User = Depends(require_perm(Permission.ROLE_OFFER)),
    db: AsyncSession = Depends(get_db),
):
    """Every event for this account, newest first.

    The point of the endpoint: the role in force right now must be traceable to
    the row that produced it. A list of current roles would not have answered
    that, which is the whole reason the column alone was not enough.
    """
    grants = await roles_core.journal(db, user_id)
    return await _with_actor_names(db, grants)


# ─────────────────────────── subject's side ───────────────────────────

@router.get("/admin/role-offers", response_model=list[PendingOfferOut])
async def open_offers(
    _: User = Depends(require_perm(Permission.ROLE_OFFER)),
    db: AsyncSession = Depends(get_db),
):
    """Every offer nobody has answered yet, newest first.

    The screen this feeds exists because an offer is a request for a decision
    that somebody else has to make, and a request nobody can see is a request
    that quietly never happened. Before this, the only trace of an unanswered
    offer was the letter — in the recipient's mailbox, where the person who
    sent it cannot look.

    Read as the latest event per (subject, role) pair rather than by selecting
    `event = 'offered'`: an offer that was later declined or withdrawn still has
    its `offered` row, and filtering on the event alone would list answers that
    already came back as if they were still pending.
    """
    from sqlalchemy import desc

    from app.models.role_grant import RoleGrant as RG

    rows = (
        await db.execute(select(RG).order_by(desc(RG.created_at), desc(RG.id)))
    ).scalars().all()

    latest: dict[tuple[uuid.UUID, str], RG] = {}
    for row in rows:
        latest.setdefault((row.subject_id, row.role), row)
    pending = [g for g in latest.values() if g.event is RoleGrantEvent.offered]
    pending.sort(key=lambda g: g.created_at, reverse=True)

    enriched = await _with_actor_names(db, pending)
    subject_ids = {g.subject_id for g in pending}
    subjects: dict[uuid.UUID, tuple[str, str | None]] = {}
    if subject_ids:
        srows = (
            await db.execute(
                select(User.id, User.display_name, User.email).where(
                    User.id.in_(subject_ids)
                )
            )
        ).all()
        subjects = {r[0]: (r[1] or "", r[2]) for r in srows}

    return [
        PendingOfferOut(
            **base.model_dump(),
            subject_id=grant.subject_id,
            subject_name=subjects.get(grant.subject_id, ("", None))[0],
            subject_contact=subjects.get(grant.subject_id, ("", None))[1],
        )
        for grant, base in zip(pending, enriched)
    ]


@router.get("/me/roles", response_model=MyRolesOut)
async def my_roles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offers = await roles_core.pending_offers(db, user.id)
    return MyRolesOut(
        roles=list(user.roles or []),
        offers=await _with_actor_names(db, offers),
    )


@router.post("/me/roles/{role}/accept", response_model=RoleGrantOut)
async def accept_offer(
    role: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        grant = await roles_core.accept(db, user, role)
    except roles_core.RoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(grant)
    return (await _with_actor_names(db, [grant]))[0]


@router.post("/me/roles/{role}/decline", response_model=RoleGrantOut)
async def decline_offer(
    role: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        grant = await roles_core.decline(db, user, role)
    except roles_core.RoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(grant)
    return (await _with_actor_names(db, [grant]))[0]


@router.get("/roles/offerable", response_model=list[str])
async def offerable_roles(
    _: User = Depends(require_perm(Permission.ROLE_OFFER)),
):
    """Which roles the admin screen may propose.

    Served rather than duplicated in the frontend: a second copy of this list
    would be wrong on the day a role is added, and wrong in the direction that
    shows a role the backend then refuses.
    """
    return list(OFFERABLE_ROLES)
