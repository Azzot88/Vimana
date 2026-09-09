"""T3.11.19 — the sender's side of the market: a request, and a subscription.

**366 posts in the dump are «кто летит в ближайшие дни ЛА — Москва?».** That is
not a failure to use the board. At a five-day median horizon the sender is right:
at the moment they look, the trip they need does not exist yet. A listing answers
a question about the present; this answers one about next week.

**Not an `Order`.** An order is half of a deal — declared value, recipient,
category, a trip it is matched to — and every one of those is a decision the
person filing a request has not made. Writing it as an order would mean inventing
four answers so the row would save.

Endpoints:
- `POST /api/requests` — file one.
- `GET /api/requests` — mine, newest first.
- `GET /api/requests/open` — what people are waiting for, for carriers deciding
  whether a corridor is worth flying. No names.
- `PATCH /api/requests/{id}` — close it, or stop the letters without closing it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.marketplace import SenderRequest
from app.models.user import User

router = APIRouter()

#: How far ahead a request may reach. Long enough for «лечу в отпуск в мае»,
#: short enough that the corridor index is not carrying rows nobody will ever
#: answer. A window is closed by its own end date, not by a sweeper.
MAX_WINDOW_DAYS = 180


class RequestIn(BaseModel):
    origin: str = Field(max_length=100)
    destination: str = Field(max_length=100)
    window_from: date
    window_to: date
    #: Free text, and the only description. Category and weight are absent on
    #: purpose: the question is whether anybody flies at all, and a form asking
    #: for a category before that is answered is a form nobody fills in.
    what: str | None = Field(default=None, max_length=300)
    notify: bool = True

    @model_validator(mode="after")
    def _window_is_a_window(self):
        if self.window_to < self.window_from:
            raise ValueError("window_to is before window_from")
        if (self.window_to - self.window_from).days > MAX_WINDOW_DAYS:
            raise ValueError(f"window longer than {MAX_WINDOW_DAYS} days")
        if self.origin.strip().upper() == self.destination.strip().upper():
            raise ValueError("origin and destination must differ")
        return self


class RequestPatch(BaseModel):
    """Both switches, separately. «Закрыл» and «не пишите мне» are different
    answers: a request kept open without letters is still a public statement
    that somebody wants this corridor, and carriers read it."""

    is_open: bool | None = None
    notify: bool | None = None


class RequestOut(BaseModel):
    id: uuid.UUID
    origin: str
    destination: str
    window_from: date
    window_to: date
    what: str | None
    notify: bool
    is_open: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CorridorDemandOut(BaseModel):
    """What people are waiting for, counted. **No names and no ids.**

    A carrier deciding whether to fly a corridor needs the number; who asked is
    the senders' business, and publishing it would turn a request into a lead
    list somebody could work through.
    """

    origin: str
    destination: str
    waiting: int


@router.post("/requests", response_model=RequestOut, status_code=201)
async def file_request(
    body: RequestIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = SenderRequest(
        sender_id=current_user.id,
        origin=body.origin.strip().upper(),
        destination=body.destination.strip().upper(),
        window_from=body.window_from,
        window_to=body.window_to,
        what=(body.what or "").strip() or None,
        notify=body.notify,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/requests", response_model=list[RequestOut])
async def my_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        (
            await db.execute(
                select(SenderRequest)
                .where(SenderRequest.sender_id == current_user.id)
                .order_by(SenderRequest.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return rows


@router.get("/requests/open", response_model=list[CorridorDemandOut])
async def corridor_demand(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Which corridors people are waiting for, and how many.

    Counted rather than listed, and requires a login like the board itself does
    not — this is aggregate, carries no identity, and a carrier weighing a route
    is exactly who it is for. Expired windows fall out on their own: the filter
    is the date, so nothing has to sweep.
    """
    today = date.today()
    rows = (
        await db.execute(
            select(
                SenderRequest.origin,
                SenderRequest.destination,
                func.count().label("waiting"),
            )
            .where(
                SenderRequest.is_open.is_(True),
                SenderRequest.window_to >= today,
            )
            .group_by(SenderRequest.origin, SenderRequest.destination)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    return [
        CorridorDemandOut(origin=r[0], destination=r[1], waiting=r[2]) for r in rows
    ]


@router.patch("/requests/{request_id}", response_model=RequestOut)
async def update_request(
    request_id: uuid.UUID,
    body: RequestPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close it, or keep it open and silent.

    Closed rather than deleted: what people asked for and did not get is the most
    useful thing this table knows, and a product that erases it on the first tidy
    loses the only record of its own unmet demand.
    """
    row = (
        await db.execute(
            select(SenderRequest).where(SenderRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None or row.sender_id != current_user.id:
        # 404 either way: whether somebody else's request exists is not a fact
        # this endpoint is entitled to confirm.
        raise HTTPException(status_code=404, detail="Request not found")
    if body.is_open is not None:
        row.is_open = body.is_open
    if body.notify is not None:
        row.notify = body.notify
    await db.commit()
    await db.refresh(row)
    return row
