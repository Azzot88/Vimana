import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.core.signing import sign_deal_event
from app.tasks.notifications import notify_deal_status
from app.models.deal import Deal, DealEvent, DealEventType, DealStatus
from app.models.marketplace import Category, Order, OrderStatus, Trip, TripInquiry, TripStatus
from app.models.user import User
from app.schemas.marketplace import DealDetailOut, DealEventOut, DealOut, OrderCreate

router = APIRouter()


class MatchBody(BaseModel):
    trip_id: uuid.UUID
    order: OrderCreate


class EventBody(BaseModel):
    event_type: str
    payload: dict | None = None


@router.post("/match", response_model=DealOut, status_code=201)
async def match_deal(
    body: MatchBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trip = await db.get(Trip, body.trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.status != TripStatus.open:
        raise HTTPException(status_code=400, detail="Trip not available")

    category_key = body.order.category.strip().lower()
    if not category_key or len(category_key) > 50:
        raise HTTPException(status_code=422, detail="Invalid category")

    # Atomic UPSERT — prevents race between concurrent matches with same new category
    stmt = pg_insert(Category).values(
        name_key=category_key, is_default=False, usage_count=1
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["name_key"],
        set_={"usage_count": Category.__table__.c.usage_count + 1},
    )
    await db.execute(stmt)

    order = Order(
        sender_id=current_user.id,
        recipient_contact=body.order.recipient_contact,
        origin=body.order.origin,
        destination=body.order.destination,
        category=category_key,
        declared_value=body.order.declared_value,
        currency=body.order.currency,
        description=body.order.description,
        deadline=body.order.deadline,
        status=OrderStatus.open,
    )
    db.add(order)
    await db.flush()

    deal = Deal(
        order_id=order.id,
        trip_id=trip.id,
        sender_id=current_user.id,
        carrier_id=trip.carrier_id,
        status=DealStatus.matched,
    )
    db.add(deal)
    await db.flush()

    order.trip_id = trip.id
    order.status = OrderStatus.matched

    event = DealEvent(
        deal_id=deal.id,
        event_type=DealEventType.created,
        actor_id=current_user.id,
        payload={"trip_id": str(trip.id), "order_id": str(order.id)},
    )
    sign_deal_event(event, current_user)
    db.add(event)

    # T1.22: link existing inquiry thread (if any) to the new deal so pre-deal
    # chat history is scoped to the deal afterwards.
    inquiry_result = await db.execute(
        select(TripInquiry).where(
            TripInquiry.trip_id == trip.id,
            TripInquiry.sender_id == current_user.id,
        )
    )
    inquiry = inquiry_result.scalar_one_or_none()
    if inquiry and inquiry.deal_id is None:
        inquiry.deal_id = deal.id

    await db.commit()
    await db.refresh(deal)
    return deal


@router.post("/{deal_id}/accept", response_model=DealOut)
async def accept_deal(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.carrier_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only carrier can accept")

    deal.status = DealStatus.accepted

    event = DealEvent(
        deal_id=deal.id,
        event_type=DealEventType.accepted,
        actor_id=current_user.id,
        payload=None,
    )
    sign_deal_event(event, current_user)
    db.add(event)

    await db.commit()
    await db.refresh(deal)
    notify_deal_status.delay(str(deal.id), deal.status.value)
    return deal


@router.post("/{deal_id}/event", response_model=DealEventOut)
async def add_event(
    deal_id: uuid.UUID,
    body: EventBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id not in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Not a deal participant")

    try:
        event_type = DealEventType(body.event_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid event_type: {body.event_type}")

    status_map = {
        DealEventType.handoff: DealStatus.in_transit,
        DealEventType.in_transit: DealStatus.in_transit,
        DealEventType.received: DealStatus.delivered,
    }
    if event_type in status_map:
        deal.status = status_map[event_type]

    event = DealEvent(
        deal_id=deal.id,
        event_type=event_type,
        actor_id=current_user.id,
        payload=body.payload,
    )
    sign_deal_event(event, current_user)
    db.add(event)

    await db.commit()
    await db.refresh(event)
    if event_type in status_map:
        notify_deal_status.delay(str(deal_id), deal.status.value)
    return event


@router.post("/{deal_id}/confirm", response_model=DealOut)
async def confirm_deal(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only sender can confirm")

    deal.status = DealStatus.confirmed

    confirmed_event = DealEvent(
        deal_id=deal.id,
        event_type=DealEventType.confirmed,
        actor_id=current_user.id,
        payload=None,
    )
    sign_deal_event(confirmed_event, current_user)
    db.add(confirmed_event)
    await db.flush()

    deal.status = DealStatus.closed

    closed_event = DealEvent(
        deal_id=deal.id,
        event_type=DealEventType.closed,
        actor_id=current_user.id,
        payload=None,
    )
    sign_deal_event(closed_event, current_user)
    db.add(closed_event)

    await db.commit()
    await db.refresh(deal)
    notify_deal_status.delay(str(deal.id), deal.status.value)
    return deal


@router.get("/{deal_id}", response_model=DealDetailOut)
async def get_deal(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id not in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Not a deal participant")

    trip = await db.get(Trip, deal.trip_id)
    order = await db.get(Order, deal.order_id)
    sender = await db.get(User, deal.sender_id)
    carrier = await db.get(User, deal.carrier_id)

    return DealDetailOut(
        id=deal.id,
        order_id=deal.order_id,
        trip_id=deal.trip_id,
        sender_id=deal.sender_id,
        carrier_id=deal.carrier_id,
        recipient_id=deal.recipient_id,
        status=deal.status.value,
        created_at=deal.created_at,
        origin=trip.origin if trip else "",
        destination=trip.destination if trip else "",
        depart_at=trip.depart_at if trip else deal.created_at,
        sender_name=sender.display_name if sender else "",
        carrier_name=carrier.display_name if carrier else "",
        cargo_description=order.description or "" if order else "",
        cargo_category=order.category if order else "",
        declared_value=order.declared_value if order else 0,
        currency=order.currency if order else "USD",
    )


@router.get("", response_model=Page[DealOut])
async def list_deals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    base = select(Deal).where(
        or_(Deal.sender_id == current_user.id, Deal.carrier_id == current_user.id)
    )
    items, next_cursor = await paginate_desc(db, base, Deal, after, clamp_limit(limit))
    return Page(items=items, next_cursor=next_cursor)
