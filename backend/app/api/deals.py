import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, is_superuser
from app.core.database import get_db
from app.core.identity import require_live_identity
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.core.notice_pin import maybe_pin_route_note
from app.core.deal_chain import (
    SealedError,
    append_deal_event,
    content_hash_of,
    verify_chain,
    verify_content,
)
from app.core.nostr_publish import get_own_relay_url
from app.core.trust import add_dealt_with, refresh_trust_counts
from app.tasks.notifications import notify_deal_status
from app.models.deal import (
    Attachment,
    Deal,
    DealChainAnchor,
    DealEventType,
    DealStatus,
    DealVaultMessage,
)
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
    require_live_identity(current_user)  # T3.12 — a lost key cannot sign a deal

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
    pinned = await maybe_pin_route_note(db, deal, trip)
    if pinned is not None:
        # T3.7 — vault content is chained from birth, system messages included.
        await db.flush()
        await append_deal_event(
            db,
            deal_id=deal.id,
            event_type=DealEventType.message_added,
            actor_id=current_user.id,
            payload={
                "message_id": str(pinned.id),
                "content_hash": content_hash_of(
                    pinned.text_ciphertext, pinned.text_nonce
                ),
                "msg_event_id": pinned.nostr_event_id,
                "is_e2e": False,
            },
            author=current_user,
        )

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

    try:
        event = await append_deal_event(
            db,
            deal_id=deal.id,
            event_type=event_type,
            actor_id=current_user.id,
            payload=body.payload,
            author=current_user,
        )
    except SealedError:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")

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

    # T3.7 — closing seals the vault: one final chained entry recording what
    # the vault contained, then `sealed_at` blocks all further appends (except
    # `dispute_opened`, which unseals — see deal_chain._ALLOWED_WHEN_SEALED).
    # The seal event is appended *before* `sealed_at` is set so the guard
    # doesn't refuse its own seal.
    message_count = (
        await db.execute(
            select(func.count())
            .select_from(DealVaultMessage)
            .where(DealVaultMessage.deal_id == deal.id)
        )
    ).scalar_one()
    file_count = (
        await db.execute(
            select(func.count())
            .select_from(Attachment)
            .join(DealVaultMessage, Attachment.message_id == DealVaultMessage.id)
            .where(DealVaultMessage.deal_id == deal.id)
        )
    ).scalar_one()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.sealed,
        actor_id=current_user.id,
        payload={"message_count": message_count, "file_count": file_count},
        author=current_user,
    )
    deal.sealed_at = datetime.now(timezone.utc)

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
    # T3.20 — where to go and check without asking us. Only relays that actually
    # accepted the event: listing the ones that refused would send an auditor to
    # look for something that is not there, and an anchor is worth exactly the
    # third parties holding it. Our own strfry appears here too when it took the
    # event, and is worth nothing evidentially — hence the split below.
    anchor_relays: list[str] = []
    anchor_third_party_relays: list[str] = []
    # Entries written after the last anchor. They are covered by `ok` (the log is
    # internally consistent) and by nothing else yet: the claim "fixed by a third
    # party" stops at `anchored_seq`, and this number is how far past it we are.
    unanchored_entries: int = 0
    # T3.7 — seal + content coverage. Coverage is honest about pre-T3.7 data:
    # messages/files created before chaining exist but were never chained.
    sealed_at: datetime | None = None
    total_messages: int = 0
    chained_messages: int = 0
    total_files: int = 0
    chained_files: int = 0
    content_ok: bool = True
    content_mismatches: list[dict] = []


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

    # Read before verify_chain/verify_content: both call `db.expire_all()`,
    # after which touching `deal` attributes would trigger a sync refresh
    # inside the async session (MissingGreenlet).
    sealed_at = deal.sealed_at

    result = await verify_chain(db, deal_id)

    # T3.7 — content pointers + coverage. `verify_chain` proves the log is
    # intact; `verify_content` proves the log still points at the stored
    # messages/files it was written for.
    content = await verify_content(db, deal_id)
    total_messages = (
        await db.execute(
            select(func.count())
            .select_from(DealVaultMessage)
            .where(DealVaultMessage.deal_id == deal_id)
        )
    ).scalar_one()
    total_files = (
        await db.execute(
            select(func.count())
            .select_from(Attachment)
            .join(DealVaultMessage, Attachment.message_id == DealVaultMessage.id)
            .where(DealVaultMessage.deal_id == deal_id)
        )
    ).scalar_one()
    result = {
        **result,
        "sealed_at": sealed_at,
        "total_messages": total_messages,
        "chained_messages": content["checked_messages"],
        "total_files": total_files,
        "chained_files": content["checked_files"],
        "content_ok": content["content_ok"],
        "content_mismatches": content["mismatches"],
    }

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
        # Only the relays that took it. `relays` records the answer of every
        # relay we tried, and reporting a refusal as a place to look would send
        # an auditor after an event that is not there.
        accepted = [url for url, ok in (anchor.relays or {}).items() if ok]
        own = get_own_relay_url()
        head_seq = result.get("head_seq")
        result = {
            **result,
            "anchored_seq": anchor.seq,
            "anchored_hash": bytes(anchor.entry_hash).hex(),
            "anchor_event_id": anchor.nostr_event_id,
            "anchored_at": anchor.created_at,
            "anchor_relays": accepted,
            # We run our own strfry, so an anchor that landed only there proves
            # nothing about us — the evidential weight is exactly this list.
            "anchor_third_party_relays": [u for u in accepted if u != own],
            "unanchored_entries": max((head_seq or 0) - anchor.seq, 0),
        }
    else:
        result = {**result, "unanchored_entries": result.get("head_seq") or 0}
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
