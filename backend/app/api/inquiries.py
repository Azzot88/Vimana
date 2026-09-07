"""T3.11.23 — the outer chat: one per person, and only one.

Was T1.22, «pre-deal chat», one thread per `(trip_id, sender_id)` — so writing
to one carrier about three trips produced three conversations with the same
person. A chat is keyed by the pair now and outlives every deal in it; the deal
is the **nested** chat (`Deal` + `DealVaultMessage`), which already existed.

Messages stay encrypted at rest (T1.21). The routes are still called
`/inquiries/*`: renaming them in the revision that changed what they address
would have made one deploy break two things for one reason.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.address import (
    AddressNotSetError,
    format_address_message,
    resolve_share_address,
)
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_asc
from app.core.rate_limit import limiter
from app.core.chats import chat_for_pair, chat_participants
from app.models.deal import Deal, DealStatus
from app.models.marketplace import Chat, ChatMessage, Trip
from app.models.user import User
from app.schemas.inquiry import InquiryMessageCreate, InquiryMessageOut, InquiryOut

router = APIRouter()


async def _get_chat_as_participant(
    chat_id: uuid.UUID, user: User, db: AsyncSession
) -> Chat:
    """T3.11.23 — the thread is a chat now, and the id in the path is its id.

    The paths kept their names: `/inquiries/...` is what the client calls, and
    renaming the route in the same revision that changes what it addresses would
    have made one deploy break two things at once for one reason.
    """
    chat = await db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if user.id not in chat_participants(chat):
        raise HTTPException(status_code=403, detail="Not a chat participant")
    return chat


@router.post("/trips/{trip_id}/inquiry", response_model=InquiryOut, status_code=201)
async def open_inquiry(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.23 — find or create the chat with this trip's carrier.

    Idempotent, and idempotent in a stronger sense than before: writing to the
    same carrier about a second trip used to open a second thread, and now lands
    in the conversation that already exists. That is the point of the revision —
    «чаты существуют в единственном числе на человека».

    The trip is echoed back rather than stored on the chat. A caller that opened
    this from a trip gets the context it came with; a message written next
    carries `about_trip_id`, which is where the trip belongs now.
    """
    trip = await db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.carrier_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Cannot open an inquiry on your own trip"
        )

    chat = await chat_for_pair(db, current_user.id, trip.carrier_id)
    await db.commit()
    await db.refresh(chat)

    # The deal to carry on in, if one is running. Newest first: several deals
    # can share a chat, and the one the two of them are in the middle of is the
    # one they mean.
    open_deal = (
        await db.execute(
            select(Deal.id)
            .where(Deal.chat_id == chat.id, Deal.status != DealStatus.closed)
            .order_by(Deal.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    carrier = await db.get(User, trip.carrier_id)

    return InquiryOut(
        id=chat.id,
        trip_id=trip_id,
        sender_id=current_user.id,
        carrier_id=trip.carrier_id,
        counterparty_name=carrier.display_name if carrier else None,
        deal_id=open_deal,
        created_at=chat.created_at,
    )


@router.get("/inquiries", response_model=list[InquiryOut])
async def list_my_inquiries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every chat this person is in, newest first.

    T3.11.23 — one row per person rather than one per trip, which is the whole
    difference: the old list showed the same carrier three times if you had
    asked about three of their trips.
    """
    result = await db.execute(
        select(Chat)
        .where(
            or_(
                Chat.user_low_id == current_user.id,
                Chat.user_high_id == current_user.id,
            )
        )
        .order_by(Chat.created_at.desc())
        .limit(100)
    )
    chats = list(result.scalars().all())

    # T3.11.23 — the deal to carry on in, for every chat at once. A chat list
    # that cannot say «there is something live in here» is a list of names, and
    # this is the field that says it.
    #
    # Batched, not per row: the alternative is one query per chat, and a person
    # with forty counterparties would pay forty round trips to draw a list.
    # Newest first inside each chat, because several deals can share one and the
    # one they are in the middle of is the one they mean.
    open_deals: dict[uuid.UUID, uuid.UUID] = {}
    deal_counts: dict[uuid.UUID, int] = {}
    if chats:
        rows = (
            await db.execute(
                select(Deal.chat_id, Deal.id, Deal.status)
                .where(Deal.chat_id.in_([c.id for c in chats]))
                .order_by(Deal.created_at.asc())
            )
        ).all()
        # Ascending, then overwritten: the last write per chat is the newest
        # deal, which is cheaper than a window function for a page of forty.
        #
        # Closed deals are counted but never carried on in: they stay in the
        # chat as cards you can open (owner's model 2026-09-07), and the count
        # is what tells the screen whether to offer a choice of deal at all.
        for chat_id, deal_id, status in rows:
            deal_counts[chat_id] = deal_counts.get(chat_id, 0) + 1
            if status != DealStatus.closed:
                open_deals[chat_id] = deal_id

    # T3.11.23 — the other person, by name. A chat list is a list of people, and
    # a person named `55468906…` is a row nobody opens. One query for the page.
    others = {
        c.id: (c.user_high_id if c.user_low_id == current_user.id else c.user_low_id)
        for c in chats
    }
    names: dict[uuid.UUID, str] = {}
    if others:
        names = dict(
            (
                await db.execute(
                    select(User.id, User.display_name).where(
                        User.id.in_(set(others.values()))
                    )
                )
            ).all()
        )

    return [
        InquiryOut(
            id=c.id,
            deal_id=open_deals.get(c.id),
            deal_count=deal_counts.get(c.id, 0),
            # Roles are not stored on a chat — the reader is one side and the
            # other person is the other, whichever way the last deal ran.
            sender_id=current_user.id,
            carrier_id=others[c.id],
            counterparty_name=names.get(others[c.id]),
            created_at=c.created_at,
        )
        for c in chats
    ]


@router.get(
    "/inquiries/{inquiry_id}/messages", response_model=Page[InquiryMessageOut]
)
async def list_messages(
    inquiry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    await _get_chat_as_participant(inquiry_id, current_user, db)
    base = select(ChatMessage).where(ChatMessage.chat_id == inquiry_id)
    items, next_cursor = await paginate_asc(
        db, base, ChatMessage, after, clamp_limit(limit)
    )
    return Page(
        items=[
            InquiryMessageOut(
                id=m.id,
                inquiry_id=m.chat_id,
                sender_id=m.sender_id,
                text=m.text,
                created_at=m.created_at,
            )
            for m in items
        ],
        next_cursor=next_cursor,
    )


@router.post(
    "/inquiries/{inquiry_id}/messages",
    response_model=InquiryMessageOut,
    status_code=201,
)
async def post_message(
    inquiry_id: uuid.UUID,
    body: InquiryMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_chat_as_participant(inquiry_id, current_user, db)
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Message text cannot be empty")

    msg = ChatMessage(
        chat_id=inquiry_id,
        sender_id=current_user.id,
        # T3.11.23 — recorded when the client says so. The foreign key is the
        # only check it needs: a trip that does not exist cannot be named, and a
        # trip that does is public anyway — this is «what I am writing about»,
        # not a claim about who may read it.
        about_trip_id=body.about_trip_id,
        text=body.text,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return InquiryMessageOut(
        id=msg.id,
        inquiry_id=msg.chat_id,
        sender_id=msg.sender_id,
        text=msg.text,
        created_at=msg.created_at,
    )


class ShareAddressBody(BaseModel):
    address_id: uuid.UUID | None = None


@router.post(
    "/inquiries/{inquiry_id}/messages/share-address",
    response_model=InquiryMessageOut,
    status_code=201,
)
@limiter.limit("5/hour")
async def share_address(
    inquiry_id: uuid.UUID,
    request: Request,
    body: ShareAddressBody = ShareAddressBody(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T1.26 / T_UX.4 A — share a receiving address into the inquiry chat."""
    await _get_chat_as_participant(inquiry_id, current_user, db)
    try:
        view = await resolve_share_address(db, current_user, body.address_id)
        text = format_address_message(view)
    except AddressNotSetError:
        raise HTTPException(
            status_code=422,
            detail="Receiving address not set — fill it in your profile first",
        )
    msg = ChatMessage(
        chat_id=inquiry_id,
        sender_id=current_user.id,
        text=text,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return InquiryMessageOut(
        id=msg.id,
        inquiry_id=msg.chat_id,
        sender_id=msg.sender_id,
        text=msg.text,
        created_at=msg.created_at,
    )
