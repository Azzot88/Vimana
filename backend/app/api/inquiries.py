"""T1.22 — pre-deal chat between a sender and a trip's carrier.

One thread per (trip_id, sender_id). Messages encrypted at rest (T1.21).
When sender creates a deal from the trip, `POST /api/deals/match` links
`inquiry.deal_id` so the chat history is scoped to the deal afterwards.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.address import AddressNotSetError, format_address_message
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_asc
from app.core.rate_limit import limiter
from app.models.marketplace import InquiryMessage, Trip, TripInquiry
from app.models.user import User
from app.schemas.inquiry import InquiryMessageCreate, InquiryMessageOut, InquiryOut

router = APIRouter()


async def _get_inquiry_as_participant(
    inquiry_id: uuid.UUID, user: User, db: AsyncSession
) -> TripInquiry:
    inquiry = await db.get(TripInquiry, inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    if user.id not in (inquiry.sender_id, inquiry.carrier_id):
        raise HTTPException(status_code=403, detail="Not an inquiry participant")
    return inquiry


@router.post("/trips/{trip_id}/inquiry", response_model=InquiryOut, status_code=201)
async def open_inquiry(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent — returns existing thread for (trip, sender) if any."""
    trip = await db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.carrier_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Cannot open an inquiry on your own trip"
        )

    existing = await db.execute(
        select(TripInquiry).where(
            TripInquiry.trip_id == trip_id,
            TripInquiry.sender_id == current_user.id,
        )
    )
    thread = existing.scalar_one_or_none()
    if thread:
        return thread

    thread = TripInquiry(
        trip_id=trip_id, sender_id=current_user.id, carrier_id=trip.carrier_id
    )
    db.add(thread)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent create raced us — return whichever won.
        await db.rollback()
        again = await db.execute(
            select(TripInquiry).where(
                TripInquiry.trip_id == trip_id,
                TripInquiry.sender_id == current_user.id,
            )
        )
        return again.scalar_one()
    await db.refresh(thread)
    return thread


@router.get("/inquiries", response_model=list[InquiryOut])
async def list_my_inquiries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All threads current user participates in (as sender or carrier)."""
    from sqlalchemy import or_

    result = await db.execute(
        select(TripInquiry)
        .where(
            or_(
                TripInquiry.sender_id == current_user.id,
                TripInquiry.carrier_id == current_user.id,
            )
        )
        .order_by(TripInquiry.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


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
    await _get_inquiry_as_participant(inquiry_id, current_user, db)
    base = select(InquiryMessage).where(InquiryMessage.inquiry_id == inquiry_id)
    items, next_cursor = await paginate_asc(
        db, base, InquiryMessage, after, clamp_limit(limit)
    )
    return Page(
        items=[
            InquiryMessageOut(
                id=m.id,
                inquiry_id=m.inquiry_id,
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
    await _get_inquiry_as_participant(inquiry_id, current_user, db)
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Message text cannot be empty")

    msg = InquiryMessage(
        inquiry_id=inquiry_id,
        sender_id=current_user.id,
        text=body.text,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return InquiryMessageOut(
        id=msg.id,
        inquiry_id=msg.inquiry_id,
        sender_id=msg.sender_id,
        text=msg.text,
        created_at=msg.created_at,
    )


@router.post(
    "/inquiries/{inquiry_id}/messages/share-address",
    response_model=InquiryMessageOut,
    status_code=201,
)
@limiter.limit("5/hour")
async def share_address(
    inquiry_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T1.26 — share user's receiving address into the inquiry chat."""
    await _get_inquiry_as_participant(inquiry_id, current_user, db)
    try:
        text = format_address_message(current_user)
    except AddressNotSetError:
        raise HTTPException(
            status_code=422,
            detail="Receiving address not set — fill it in your profile first",
        )
    msg = InquiryMessage(
        inquiry_id=inquiry_id,
        sender_id=current_user.id,
        text=text,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return InquiryMessageOut(
        id=msg.id,
        inquiry_id=msg.inquiry_id,
        sender_id=msg.sender_id,
        text=msg.text,
        created_at=msg.created_at,
    )
