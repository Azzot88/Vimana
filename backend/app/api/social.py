import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.trust import add_invited
from app.models.social import Connection, InviteLink
from app.models.user import User
from app.schemas.social import ConnectionOut, InviteLinkOut, MyInviteOut

router = APIRouter()

INVITE_TTL_DAYS = 14


class InviteBody(BaseModel):
    recipient_contact: str | None = None


@router.post("/invites", response_model=InviteLinkOut, status_code=201)
async def create_invite(
    body: InviteBody = InviteBody(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invite = InviteLink(
        creator_id=current_user.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


@router.get("/invites/mine", response_model=list[MyInviteOut])
async def list_my_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InviteLink)
        .where(InviteLink.creator_id == current_user.id)
        .order_by(InviteLink.created_at.desc())
    )
    invites = result.scalars().all()

    now = datetime.now(timezone.utc)
    accepted_names: dict[uuid.UUID, str] = {}
    accepted_ids = [inv.used_by for inv in invites if inv.used_by is not None]
    if accepted_ids:
        users_result = await db.execute(select(User).where(User.id.in_(accepted_ids)))
        for u in users_result.scalars().all():
            accepted_names[u.id] = u.display_name

    out: list[MyInviteOut] = []
    for inv in invites:
        expires_at = inv.expires_at.replace(tzinfo=timezone.utc) if inv.expires_at.tzinfo is None else inv.expires_at
        if inv.used_by is not None:
            status = "accepted"
        elif expires_at < now:
            status = "expired"
        else:
            status = "pending"
        out.append(
            MyInviteOut(
                token=inv.token,
                created_at=inv.created_at,
                expires_at=inv.expires_at,
                status=status,
                accepted_by_display_name=accepted_names.get(inv.used_by) if inv.used_by else None,
            )
        )
    return out


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(InviteLink).where(InviteLink.token == token))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite expired")
    if invite.creator_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot accept your own invite")
    # Idempotent per user — re-accept by the same user is a no-op success.
    # Guards against double-click, React StrictMode double-effect, retry.
    if invite.used_by == current_user.id:
        return {"ok": True}

    # Atomic claim: only unclaimed invite can be updated
    claim = await db.execute(
        update(InviteLink)
        .where(InviteLink.token == token, InviteLink.used_by.is_(None))
        .values(used_by=current_user.id)
    )
    if claim.rowcount == 0:
        # Race — either another user claimed between our SELECT and UPDATE,
        # or the same user claimed concurrently (double-fire). Read only the
        # winning user_id column — avoids ORM refresh + greenlet issues.
        recheck = await db.execute(
            select(InviteLink.used_by).where(InviteLink.token == token)
        )
        winner_id = recheck.scalar_one_or_none()
        if winner_id == current_user.id:
            return {"ok": True}
        raise HTTPException(status_code=409, detail="Invite already used")

    try:
        db.add(Connection(
            user_id=invite.creator_id,
            connected_user_id=current_user.id,
            invite_token=token,
        ))
        db.add(Connection(
            user_id=current_user.id,
            connected_user_id=invite.creator_id,
            invite_token=token,
        ))
        # T2.4 — Trust graph: `invited` edge (symmetric).
        await add_invited(
            db,
            inviter_id=invite.creator_id,
            invitee_id=current_user.id,
            invite_token=token,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return {"ok": True}


@router.get("/me/connections", response_model=list[ConnectionOut])
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Connection)
        .where(Connection.user_id == current_user.id)
        .options(selectinload(Connection.connected_user))
    )
    connections = result.scalars().all()
    return connections
