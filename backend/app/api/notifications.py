"""T_UX.29 pt.7 — the bell, and what is behind it.

Four questions and no more: how many did I miss, what were they, I have seen
these, and — separately — here is a browser that would like to be pushed to.

The read model deserves a word. «Прочитано» here does not mean «somebody clicked
it»; it means **this was shown to them**. The deal screen clears its own deal on
every beat while it is open and visible (`DealVaultPage`), which is how the
owner's rule lands in code: «если изменения произошли в активном окне, их статусы
показывать не нужно». Anything left unread is, by construction, something nobody
was looking at.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.notification import Notification, PushSubscription
from app.models.user import User

router = APIRouter()


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    deal_id: uuid.UUID | None
    trip_id: uuid.UUID | None
    payload: dict | None
    created_at: datetime
    read_at: datetime | None


class UnreadOut(BaseModel):
    unread: int


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The panel, newest first.

    Read ones are included by default: the panel answers «что происходило», and
    a list that empties itself the moment you look at it cannot be re-read by
    somebody who closed it too fast.
    """
    q = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = (
        await db.execute(q.order_by(Notification.created_at.desc()).limit(limit))
    ).scalars().all()
    return rows


@router.get("/notifications/unread-count", response_model=UnreadOut)
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The number on the bell. Its own endpoint because it is asked far more
    often than the list is opened, and counting is cheaper than serialising."""
    total = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None),
            )
        )
    ).scalar_one()
    return UnreadOut(unread=total)


class ReadBody(BaseModel):
    """What to mark. All three are optional and they compose: no field at all
    means «everything», which is what the «прочитать все» button sends."""

    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    deal_id: uuid.UUID | None = None


@router.post("/notifications/read", response_model=UnreadOut)
async def mark_read(
    body: ReadBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark as seen, always scoped to the caller.

    `user_id` is in the WHERE clause and not merely checked: the ids come from a
    client, and a statement that could touch somebody else's row if the check
    were forgotten is a statement waiting for the day it is.
    """
    q = update(Notification).where(
        Notification.user_id == current_user.id,
        Notification.read_at.is_(None),
    )
    if body.ids:
        q = q.where(Notification.id.in_(body.ids))
    if body.deal_id:
        q = q.where(Notification.deal_id == body.deal_id)
    await db.execute(q.values(read_at=datetime.now(timezone.utc)))
    await db.commit()
    return await unread_count(current_user=current_user, db=db)


class PushBody(BaseModel):
    endpoint: str = Field(max_length=500)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


@router.post("/notifications/push", status_code=204)
async def subscribe_push(
    body: PushBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Keep a browser's push endpoint. **Nothing sends to it yet.**

    Collected from the day the button exists so that switching delivery on later
    is a worker task and a pair of VAPID keys, not a migration plus a consent
    flow nobody has given. The endpoint is the identity of the row — a browser
    re-issues it on rotation, and the same account on two devices has two.
    """
    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = current_user.id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
    else:
        db.add(
            PushSubscription(
                user_id=current_user.id,
                endpoint=body.endpoint,
                p256dh=body.p256dh,
                auth=body.auth,
            )
        )
    await db.commit()
