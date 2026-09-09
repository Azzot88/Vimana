import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.database import get_db
from app.core.identity import require_live_identity
from app.core.nostr_publish import (
    build_platform_trip_event as build_nostr_event,
    is_publish_enabled,
)
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.core.trip_legs import (
    LegChainError,
    head_and_tail,
    last_departure,
    normalise_legs,
)
from app.models.address import MeetingPlace, ReceivingAddress
from app.models.marketplace import ChatMessage, Trip, TripLeg, TripStatus
from app.models.user import User
from app.schemas.marketplace import TripCreate, TripLegOut, TripOut

router = APIRouter()


def _services_with_derived(body: TripCreate) -> list[str] | None:
    """T3.11.22 — `domestic_shipping` follows from the handover method.

    The three levels are a narrowing, not three answers to one question:
    *what I do* → *how I hand over* → *which service*. But only one of them is
    worth asking twice, and it is not the coarse one: a carrier who says the
    destination handover is `local_post` has already said they post it on.

    So the service is **derived on write** rather than gated in the form. The
    carrier answers once, the coarse level is computed, and the two can no
    longer contradict each other — which is the actual defect here, not the
    number of levels.

    Called by: `_apply_terms`, i.e. both `create_trip` and `update_trip`.
    """
    services = list(body.services or [])
    posts_it_on = bool(
        body.handover_destination
        and "local_post" in body.handover_destination.methods
    )
    if posts_it_on and "domestic_shipping" not in services:
        services.append("domestic_shipping")
    return services or None


async def _assert_owns_referenced_places(
    body: TripCreate, user: User, db: AsyncSession
) -> None:
    """Every address and meeting place the trip points at belongs to the caller.

    404 rather than 403 for a row that exists under another account, matching
    the addresses and meeting-places endpoints: telling a stranger "this id is
    real but not yours" answers a question they had no business asking.

    Called by: `create_trip`, `update_trip`.
    """
    wanted_addresses: set[uuid.UUID] = set()
    wanted_places: set[uuid.UUID] = set()
    for side in (body.handover_origin, body.handover_destination):
        if side is None:
            continue
        if side.address_id:
            wanted_addresses.add(side.address_id)
        if side.meeting_place_id:
            wanted_places.add(side.meeting_place_id)

    for ids, model, what in (
        (wanted_addresses, ReceivingAddress, "Address"),
        (wanted_places, MeetingPlace, "Meeting place"),
    ):
        if not ids:
            continue
        owned = set(
            (
                await db.execute(
                    select(model.id).where(
                        model.id.in_(ids), model.user_id == user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        if owned != ids:
            raise HTTPException(status_code=404, detail=f"{what} not found")


def _apply_terms(trip: Trip, body: TripCreate, carriage_fallback: str | None) -> None:
    """Everything a trip says about itself, written onto the row.

    Shared by create and edit so the two cannot drift. That mattered the moment
    editing existed: a field added to the form and to `create_trip` alone would
    save on publication and silently revert on the first edit, which reads as
    the platform losing an answer the carrier gave.

    The route is **not** here — it is normalised before this is called, and the
    denormalised head is derived from it.

    Called by: `create_trip`, `update_trip`.
    """
    trip.capacity = body.capacity
    trip.allowed_categories = body.allowed_categories
    trip.price_per_kg = body.price_per_kg
    trip.min_deal_price = body.min_deal_price
    trip.currency = body.currency
    trip.max_declared_value = body.max_declared_value
    trip.max_declared_value_currency = body.max_declared_value_currency
    trip.space_kind = body.space_kind
    trip.size_hint = body.size_hint
    # `mode="json"` because the column is JSON and the side carries UUIDs: the
    # default dump keeps them as `UUID` objects, which asyncpg cannot write into
    # a JSON column and which fail at serialisation, not at validation.
    trip.handover_origin = (
        body.handover_origin.model_dump(mode="json") if body.handover_origin else None
    )
    trip.handover_destination = (
        body.handover_destination.model_dump(mode="json")
        if body.handover_destination
        else None
    )
    trip.excluded = body.excluded
    trip.services = _services_with_derived(body)
    trip.payment_model = body.payment_model
    trip.payment_systems = body.payment_systems
    # T3.11.18 — the ceiling and who pays for the goods. Written together with
    # the service they belong to; `TripCreate` refuses one without the other.
    trip.buyout_limit = body.buyout_limit
    trip.buyout_paid_by = body.buyout_paid_by
    # T_UX.15 — the carrier's standing rules are **copied** into the trip, not
    # referenced. Edited later they must not rewrite what a sender read when
    # they chose this trip. `None` means "use my template"; an explicit empty
    # string means this trip carries no rules.
    trip.carriage_rules = (
        body.carriage_rules if body.carriage_rules is not None else carriage_fallback
    )


@router.post("", response_model=TripOut, status_code=201)
async def create_trip(
    body: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.can_carry:
        raise HTTPException(status_code=403, detail="Carrier capability required")
    require_live_identity(current_user)  # T3.12 — a lost key cannot sign a trip

    # T3.11.15 — the chain is normalised before anything is built from it:
    # codes upper-cased (T_PERF.1 — the filter compares exactly, so a leg stored
    # as `dxb` is invisible to every search for `DXB`), order assigned densely,
    # legs checked not to travel backwards in time.
    try:
        legs = normalise_legs([leg.model_dump() for leg in body.legs])
    except LegChainError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    head_origin, tail_destination, first_departure = head_and_tail(legs)

    # T3.11.07 — a handover end may point at one of the carrier's addresses or
    # meeting places. Ownership is checked here because a schema cannot know
    # whose row an id is, and an unchecked id is a way to publish a stranger's
    # home address on a public board.
    await _assert_owns_referenced_places(body, current_user, db)

    trip = Trip(
        carrier_id=current_user.id,
        # Denormalised head of the chain. Search, the board, the Nostr event and
        # the T3.11.06 countdown all stand on these three; they are derived, not
        # submitted, so they cannot disagree with the legs.
        origin=head_origin,
        destination=tail_destination,
        depart_at=first_departure,
        # T3.11.16 — when this stops being a listing. Derived like the three
        # above, so it cannot disagree with the legs it comes from.
        expires_at=last_departure(legs),
        status=TripStatus.open,
    )
    _apply_terms(trip, body, current_user.carriage_rules)
    # Cascade `all, delete-orphan`: the legs are written by the same commit and
    # a leg outliving its trip would be a record of nothing.
    trip.legs = [TripLeg(**leg) for leg in legs]
    db.add(trip)
    await db.commit()
    # Full refresh rather than `refresh(trip, ["legs"])`. Naming attributes
    # would refresh only those and leave `created_at` — a server-side default
    # never loaded on this instance — unloaded, which in an async session
    # raises at serialisation instead of lazy-loading. The `legs` collection
    # comes along regardless: refresh honours the `selectin` loader on the
    # mapper.
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


@router.patch("/{trip_id}", response_model=TripOut)
async def update_trip(
    trip_id: uuid.UUID,
    body: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.07 — edit a published trip (owner's request 2026-09-06).

    **The same trip, not a new one.** The obvious shortcut — cancel and
    republish — changes the id, and the id is what every inquiry, every deal and
    every Nostr event points at: a carrier fixing a typo in their departure hour
    would silently orphan the conversation they were having about it. So the row
    is updated in place and the chain is rebuilt on it.

    **Whole body, not a patch of fields.** `TripCreate` is what the wizard
    already produces and it always sends every answer, so a partial body would
    be a second shape to validate with no caller. `PATCH` rather than `PUT` only
    because the URL names an existing resource and the verb is the one clients
    reach for; the semantics are a full replacement and this docstring is where
    that is written down.

    **Only while it is `open`.** A matched or completed trip is no longer a
    listing — it is part of what two people agreed to, and rewriting it after
    the fact is the one thing `D-COMPLIANCE-STANCE` is about: the record has to
    say what was true when it was read. Cancelled trips stay cancelled; the way
    back is a new publication.

    `carriage_rules` falls back to the account template exactly as it does on
    creation. That is deliberate and slightly lossy: a carrier who publishes
    with their template, then changes the template, then edits the trip will get
    the new one. The alternative — keeping the old copy — means an edit cannot
    refresh the rules at all, and the carrier has no other way to do it.
    """
    trip = (
        await db.execute(select(Trip).where(Trip.id == trip_id))
    ).scalar_one_or_none()
    # 404 rather than 403 for somebody else's trip: which trips exist is public,
    # but which of them are yours is not something a stranger gets to probe.
    if trip is None or trip.carrier_id != current_user.id:
        raise HTTPException(status_code=404, detail="Trip not found")
    require_live_identity(current_user)  # T3.12 — a lost key cannot sign a trip
    if trip.status != TripStatus.open:
        raise HTTPException(
            status_code=409,
            detail="Only an open trip can be edited",
        )

    try:
        legs = normalise_legs([leg.model_dump() for leg in body.legs])
    except LegChainError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    head_origin, tail_destination, first_departure = head_and_tail(legs)

    await _assert_owns_referenced_places(body, current_user, db)

    # T3.11.16 — a moved flight is the one edit somebody else has to hear about.
    # Read **before** the row is overwritten: afterwards there is nothing left
    # to compare against, which is why «перенос» could not be told from any other
    # edit until now.
    was_departure = trip.depart_at

    trip.origin = head_origin
    trip.destination = tail_destination
    trip.depart_at = first_departure
    trip.expires_at = last_departure(legs)
    _apply_terms(trip, body, current_user.carriage_rules)
    # Replaced wholesale rather than diffed. `leg_order` is dense and assigned by
    # `normalise_legs`, so matching old rows to new ones would mean guessing
    # which leg the carrier meant to keep — and guessing wrong leaves a chain
    # that is off by one city.
    #
    # **In two flushes, and that is not optional.** `delete-orphan` removes the
    # old rows, but the unit of work does not order that removal before an
    # insert that reuses the same key: the new leg 0 goes in while the old leg 0
    # is still there and hits `uq_trip_legs_order`. Every edit failed with a
    # database error until the delete got a flush of its own.
    trip.legs.clear()
    await db.flush()
    trip.legs = [TripLeg(**leg) for leg in legs]

    await db.commit()
    await db.refresh(trip)

    # T3.5 — the relays hold the version that was published. Re-publishing is
    # enqueued for the same reason it is on creation: a trip whose board card
    # and whose Nostr event disagree is worse than one that is only on the
    # board. The task itself checks the flag.
    from app.tasks.nostr_publish import publish_trip_to_nostr
    try:
        publish_trip_to_nostr.delay(str(trip.id))
    except Exception:
        # Broker unreachable in dev — the edit still landed in Postgres.
        pass

    # T3.11.16 — «перенос»: the carrier moved the flight, and the people whose
    # deals ride on it are told. Only when the departure actually changed —
    # every other edit is the carrier's own business, and a letter for each of
    # them would teach senders to ignore the one that matters.
    if trip.depart_at != was_departure:
        from app.tasks.notifications import notify_trip_rescheduled

        try:
            notify_trip_rescheduled.delay(
                str(trip.id),
                was_departure.isoformat(),
                trip.depart_at.isoformat(),
            )
        except Exception:
            # Same posture as the publish above: the edit is saved either way,
            # and a broker that is down must not fail a carrier's correction.
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


@router.get("/ask-counts", response_model=dict[str, int])
async def ask_counts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.23 — how many people have asked about each of my trips.

    The carrier's panel prints this next to every live trip, and it used to come
    from counting threads: one thread per `(trip, sender)` made the count free.
    With one chat per person there is no per-trip thread left to count, so the
    question is answered where the trip actually is now — on the message that
    raised it (`ChatMessage.about_trip_id`).

    **Distinct chats, not messages.** Somebody who writes four times about one
    trip has asked once; counting messages would turn a talkative sender into a
    queue of four.

    Declared above the `{trip_id}` routes. There is no bare `GET /trips/{id}`
    today, so nothing shadows it yet — the placement is insurance for the day
    somebody adds one, because FastAPI matches in declaration order and the
    failure would be a 422 about an invalid uuid named «ask-counts».

    Only the caller's own trips — the number is a fact about their listing, and
    on somebody else's it is a demand figure they did not publish.
    """
    rows = (
        await db.execute(
            select(
                ChatMessage.about_trip_id,
                func.count(func.distinct(ChatMessage.chat_id)),
            )
            .join(Trip, Trip.id == ChatMessage.about_trip_id)
            .where(Trip.carrier_id == current_user.id)
            .group_by(ChatMessage.about_trip_id)
        )
    ).all()
    return {str(trip_id): count for trip_id, count in rows}

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
        # T3.11.16 — the board is open trips that have not flown yet. Expiry is
        # a filter rather than a status change: nobody cancelled the trip and it
        # did not fail, it simply happened, and rewriting `status` to say
        # otherwise would put a false word in the carrier's own history. A trip
        # published before the column existed has `expires_at IS NULL` and keeps
        # being shown — hiding rows we cannot date would be guessing.
        stmt = select(Trip).where(
            Trip.status == TripStatus.open,
            or_(
                Trip.expires_at.is_(None),
                Trip.expires_at >= datetime.now(timezone.utc),
            ),
        )
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
                    max_declared_value=t.max_declared_value,
                    max_declared_value_currency=t.max_declared_value_currency,
                    # T3.11.15 — a trip whose chain is invisible in the listing
                    # is a trip whose second flight nobody can find, and the
                    # second flight is present in 36.6 % of real posts.
                    space_kind=t.space_kind,
                    size_hint=t.size_hint,
                    handover_origin=t.handover_origin,
                    handover_destination=t.handover_destination,
                    legs=[TripLegOut.model_validate(leg) for leg in t.legs],
                    excluded=t.excluded,
                    services=t.services,
                    payment_model=t.payment_model,
                    payment_systems=t.payment_systems,
                    buyout_limit=t.buyout_limit,
                    buyout_paid_by=t.buyout_paid_by,
                    carriage_rules=t.carriage_rules,
                    status=t.status.value if hasattr(t.status, "value") else str(t.status),
                    created_at=t.created_at,
                    # T3.11.16 — when the listing stops being one: the card
                    # can say «сегодня последний день» instead of leaving the
                    # reader to work it out from the legs.
                    expires_at=t.expires_at,
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
