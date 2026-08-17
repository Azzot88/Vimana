import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.database import get_db
from app.core.identity import require_live_identity
from app.core.nostr_publish import (
    build_platform_trip_event as build_nostr_event,
    is_publish_enabled,
)
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.models.marketplace import Trip, TripStatus
from app.models.user import User
from app.schemas.marketplace import TripCreate, TripOut

router = APIRouter()


@router.post("", response_model=TripOut, status_code=201)
async def create_trip(
    body: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.can_carry:
        raise HTTPException(status_code=403, detail="Carrier capability required")
    require_live_identity(current_user)  # T3.12 — a lost key cannot sign a trip

    # Normalised on write (T_PERF.1). The filter compares codes exactly, so the
    # column has to hold one canonical form — otherwise a trip stored as `dxb`
    # is invisible to every search for `DXB`, which is what the API accepts.
    # `AirportSelect` already sends upper-case; this covers a direct POST, and
    # it is the write side that should decide the shape, not each reader.
    trip = Trip(
        carrier_id=current_user.id,
        origin=body.origin.strip().upper(),
        destination=body.destination.strip().upper(),
        depart_at=body.depart_at,
        capacity=body.capacity,
        allowed_categories=body.allowed_categories,
        # T3.35 — the carrier's baseline terms travel with the listing, so a
        # sender can compare two trips on a corridor before opening a chat.
        price_per_kg=body.price_per_kg,
        min_deal_price=body.min_deal_price,
        currency=body.currency,
        allowed_handover_methods=body.allowed_handover_methods,
        max_declared_value=body.max_declared_value,
        # T_UX.15 — the carrier's standing rules are **copied** into the trip,
        # not referenced. Edited later they must not rewrite what a sender read
        # when they chose this trip. `None` means "use my template"; an explicit
        # empty string means this trip carries no rules.
        carriage_rules=(
            body.carriage_rules
            if body.carriage_rules is not None
            else current_user.carriage_rules
        ),
        status=TripStatus.open,
    )
    db.add(trip)
    await db.commit()
    await db.refresh(trip)

    # T3.5 — fire-and-forget publish. Task itself checks the flag; enqueuing
    # unconditionally keeps the request path free of env branches.
    from app.tasks.nostr_publish import publish_trip_to_nostr
    try:
        publish_trip_to_nostr.delay(str(trip.id))
    except Exception:
        # Broker unreachable in dev — the trip still exists in Postgres.
        pass

    return trip


@router.post("/{trip_id}/cancel", response_model=TripOut)
async def cancel_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T_UX.19 — withdraw a published trip.

    Until now a trip could be created and never taken back. Plans change, and a
    carrier whose flight moved had no way to say so: the listing stayed up and
    senders kept writing to it. Withdrawing is the control the panel was
    missing, not a nicety.

    Cancelled rather than deleted. Somebody may already have opened a
    conversation about this trip, and deleting the row would leave that thread
    pointing at nothing; a cancelled trip still explains itself.
    """
    trip = await db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.carrier_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your trip")
    if trip.status not in (TripStatus.draft, TripStatus.open):
        # A matched trip is somebody else's plan too — withdrawing it silently
        # would cancel their delivery without telling them.
        raise HTTPException(
            status_code=409, detail="Only an open trip can be withdrawn"
        )

    trip.status = TripStatus.cancelled
    await db.commit()
    await db.refresh(trip)
    return trip


@router.get("", response_model=Page[TripOut])
async def list_trips(
    origin: str | None = None,
    destination: str | None = None,
    date: date | None = None,
    # T_UX.18 — every place a trip is shown makes the carrier's name a link, and
    # the page behind it is "everything this carrier is flying". Without a filter
    # that page would have to pull the whole board and sift it client-side.
    carrier_id: uuid.UUID | None = None,
    # T_UX.19 — the board is open trips only, and that is right for a board. But
    # "my published trips" in a profile is a history: it has to contain the ones
    # that were withdrawn and the ones that flew. Asking for anything other than
    # `open` is therefore allowed **only about yourself** — a withdrawn trip is
    # no longer a public listing, and letting strangers enumerate them would
    # publish a carrier's changes of plan.
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    after: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    own = (
        current_user is not None
        and carrier_id is not None
        and carrier_id == current_user.id
    )
    if status is not None and not own:
        raise HTTPException(
            status_code=403, detail="Only your own trips can be listed by status"
        )
    if status is None:
        stmt = select(Trip).where(Trip.status == TripStatus.open)
    elif status == "all":
        stmt = select(Trip)
    else:
        try:
            stmt = select(Trip).where(Trip.status == TripStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown trip status")

    # Exact match, not `ilike '%code%'` (T_PERF.1). `origin`/`destination` hold
    # IATA codes — `AirportSelect` can only emit one — so a substring match was
    # both slower (a leading wildcard cannot use an index) and wrong: `?origin=A`
    # matched every airport with an A in it. The query is upper-cased because a
    # hand-typed `dxb` should still find `DXB`; stored values come from the
    # picker and are already upper-case.
    if origin:
        stmt = stmt.where(Trip.origin == origin.strip().upper())
    if destination:
        stmt = stmt.where(Trip.destination == destination.strip().upper())
    if carrier_id:
        stmt = stmt.where(Trip.carrier_id == carrier_id)
    if date:
        # Half-open UTC day instead of `cast(depart_at, Date) = :date`: a
        # function on the column rules the index out for every row.
        day_start = datetime.combine(date, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(
            Trip.depart_at >= day_start,
            Trip.depart_at < day_start + timedelta(days=1),
        )

    items, next_cursor = await paginate_desc(db, stmt, Trip, after, clamp_limit(limit))

    # Enrich with carrier name + UBA. One additional query batched by ids.
    from app.core.uba import level_of
    from app.models.user import User

    if items:
        carrier_ids = list({t.carrier_id for t in items})
        rows = await db.execute(
            select(
                User.id,
                User.display_name,
                User.business_activity_level,
                User.key_lost_at,
            ).where(User.id.in_(carrier_ids))
        )
        by_id = {r.id: r for r in rows}
        out: list[TripOut] = []
        for t in items:
            row = by_id.get(t.carrier_id)
            uba = int(row.business_activity_level) if row and row.business_activity_level is not None else None
            out.append(
                TripOut(
                    id=t.id,
                    carrier_id=t.carrier_id,
                    carrier_name=row.display_name if row else None,
                    carrier_uba=uba,
                    carrier_uba_level=level_of(uba) if uba is not None else None,
                    carrier_key_lost=bool(row and row.key_lost_at is not None),
                    origin=t.origin,
                    destination=t.destination,
                    depart_at=t.depart_at,
                    capacity=t.capacity,
                    allowed_categories=t.allowed_categories,
                    # T3.35 — the listing is the whole point of storing a
                    # baseline: two trips on one corridor have to be comparable
                    # before anyone opens a chat. This block is hand-built
                    # rather than `from_attributes`, so a new column reaches the
                    # POST response for free and the listing only if named here.
                    price_per_kg=t.price_per_kg,
                    min_deal_price=t.min_deal_price,
                    currency=t.currency,
                    allowed_handover_methods=t.allowed_handover_methods,
                    max_declared_value=t.max_declared_value,
                    carriage_rules=t.carriage_rules,
                    status=t.status.value if hasattr(t.status, "value") else str(t.status),
                    created_at=t.created_at,
                    nostr_event_id=t.nostr_event_id,
                    nostr_published_at=t.nostr_published_at,
                )
            )
        return Page(items=out, next_cursor=next_cursor)
    return Page(items=[], next_cursor=next_cursor)


@router.get("/{trip_id}/nostr-event")
async def get_trip_nostr_event(
    trip_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.5 — return the Nostr event JSON for a trip.

    Two states:
    - `nostr_event_id` is set → return the event as it would be published
      (regenerated from current state — content stays stable per NIP-99
      replaceable semantics).
    - Publish disabled or the carrier lacks a server-held nsec → 503.
    """
    if not is_publish_enabled():
        raise HTTPException(
            status_code=503, detail="Nostr publish is disabled on this instance"
        )
    trip = await db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    carrier = await db.get(User, trip.carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")

    import os as _os

    event = build_nostr_event(
        trip,
        carrier,
        _os.getenv("VIMANA_PUBLIC_URL", "https://vimana.dealvault.club"),
    )
    if event is None:
        raise HTTPException(
            status_code=503,
            detail="PLATFORM_PUBLISH_NSEC not configured",
        )
    return event
