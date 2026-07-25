import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, is_superuser
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.core.notice_pin import maybe_pin_route_note
from app.core.deal_chain import append_deal_event, verify_chain
from app.core.trust import add_dealt_with, refresh_trust_counts
from app.tasks.notifications import notify_deal_status
from app.models.deal import Deal, DealChainAnchor, DealEventType, DealStatus
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

    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.created,
        actor_id=current_user.id,
        payload={"trip_id": str(trip.id), "order_id": str(order.id)},
        author=current_user,
    )

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

    # T_UX.2 pt.4 — pin corridor note as system-message if the corridor is
    # flagged. Informational only; never blocks the match.
    await maybe_pin_route_note(db, deal, trip)

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

    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.accepted,
        actor_id=current_user.id,
        author=current_user,
    )

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

    event = await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=event_type,
        actor_id=current_user.id,
        payload=body.payload,
        author=current_user,
    )

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

    # Two entries in one transaction: `append_deal_event` flushes, so the second
    # call reads the first as its chain head and links to it.
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.confirmed,
        actor_id=current_user.id,
        author=current_user,
    )

    deal.status = DealStatus.closed

    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.closed,
        actor_id=current_user.id,
        author=current_user,
    )

    # T2.4 — Trust graph: `dealt_with` edge on close (symmetric).
    await add_dealt_with(db, deal)
    await refresh_trust_counts(db, deal.sender_id)
    await refresh_trust_counts(db, deal.carrier_id)

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
        sender_npub=sender.nostr_pubkey if sender else None,
        carrier_npub=carrier.nostr_pubkey if carrier else None,
        cargo_description=order.description or "" if order else "",
        cargo_category=order.category if order else "",
        declared_value=order.declared_value if order else 0,
        currency=order.currency if order else "USD",
    )


class ChainStatusOut(BaseModel):
    ok: bool
    length: int
    head_seq: int | None = None
    head_hash: str | None = None
    broken_at: int | None = None
    reason: str | None = None
    anchored_seq: int | None = None
    anchored_hash: str | None = None
    anchor_event_id: str | None = None
    anchored_at: datetime | None = None


@router.get("/{deal_id}/chain", response_model=ChainStatusOut)
async def get_deal_chain(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.6 — recompute the deal's hash chain and report its anchoring status.

    Two independent claims, deliberately reported separately:

    - `ok` — the log is internally consistent (nothing edited, reordered, or
      removed *behind our back*).
    - `anchored_seq` / `anchor_event_id` — how far the log has been published to
      relays we do not control. Everything at or below `anchored_seq` can no
      longer be rewritten by us either; anything above it is covered only by the
      first claim.

    A caller who needs proof rather than reassurance should compare
    `anchored_hash` against the anchor event fetched from a third-party relay.

    Access mirrors `GET /deals/{id}` (sender/carrier), plus superuser. Arbiter
    access runs through the grant-gated admin surface — see follow-up in TASKS.
    """
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id not in (deal.sender_id, deal.carrier_id) and not is_superuser(
        current_user
    ):
        raise HTTPException(status_code=403, detail="Not a deal participant")

    result = await verify_chain(db, deal_id)

    anchor = (
        (
            await db.execute(
                select(DealChainAnchor)
                .where(DealChainAnchor.deal_id == deal_id)
                .order_by(DealChainAnchor.seq.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if anchor is not None:
        result = {
            **result,
            "anchored_seq": anchor.seq,
            "anchored_hash": bytes(anchor.entry_hash).hex(),
            "anchor_event_id": anchor.nostr_event_id,
            "anchored_at": anchor.created_at,
        }
    return ChainStatusOut(**result)


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
