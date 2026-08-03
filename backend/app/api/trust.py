"""T2.4 — Trust Graph HTTP endpoints, plus the public identity page (T3.18)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.core.airports import route_distance_km
from app.core.database import get_db
from app.core.permissions import require_visible
from app.core.storage import get_presigned_url
from app.core.trust import bfs_circles, distance_between
from app.core.uba import level_of
from app.models.deal import Deal, DealChainAnchor, DealEvent, DealStatus
from app.models.marketplace import Trip
from app.models.trust import TrustEdge, TrustEdgeKind
from app.models.user import User
from app.models.verification import VerificationBadge

router = APIRouter()


class TrustCirclesOut(BaseModel):
    depth: int
    kind: str | None
    circles: dict[str, list[uuid.UUID]]  # {"1": [...], "2": [...]}
    total_reachable: int


class TrustMetricsOut(BaseModel):
    subject_id: uuid.UUID
    verifications_issued_count: int
    verifications_received_count: int
    dealt_with_count: int
    distance_from_viewer: int | None  # None if not authenticated or not connected
    # T_TRUST.1 — a counter says nothing about time, and three vouches from four
    # years ago is a different statement from three from last month. The date of
    # the newest live vouch is the cheapest way to tell them apart.
    last_vouched_at: datetime | None = None


@router.get("/me/trust-circle", response_model=TrustCirclesOut)
async def my_trust_circle(
    depth: int = Query(3, ge=1, le=6),
    kind: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed_kind = None
    if kind:
        try:
            parsed_kind = TrustEdgeKind(kind)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"kind must be one of: {[k.value for k in TrustEdgeKind]}",
            )
    levels = await bfs_circles(
        db, root_id=current_user.id, depth=depth, kind=parsed_kind
    )
    # Skip level 0 (self) from output; keep 1..depth.
    circles_out = {str(k): v for k, v in levels.items() if k > 0}
    total = sum(len(v) for v in circles_out.values())
    return TrustCirclesOut(
        depth=depth,
        kind=parsed_kind.value if parsed_kind else None,
        circles=circles_out,
        total_reachable=total,
    )


@router.get("/users/{user_id}/trust-metrics", response_model=TrustMetricsOut)
async def user_trust_metrics(
    user_id: uuid.UUID,
    # T3.18 — optional, which is what the annotation always claimed:
    # `get_current_user` never returns None, so an anonymous caller got a 401
    # from a signature that said the viewer might be absent. These are the same
    # counters the public identity page shows, so requiring a session here and
    # not there was a difference without a reason. Anonymous simply gets no
    # `distance_from_viewer` — there is no viewer to measure from.
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # T3.18 — the same gate as the identity page. Without it `hidden` would hide
    # the page and leave the numbers on it readable one URL over.
    require_visible(user, current_user)

    distance: int | None = None
    if current_user is not None and current_user.id != user_id:
        distance = await distance_between(
            db, root_id=current_user.id, target_id=user_id, max_depth=6
        )

    return TrustMetricsOut(
        subject_id=user_id,
        verifications_issued_count=user.verifications_issued_count,
        verifications_received_count=user.verifications_received_count,
        dealt_with_count=user.dealt_with_count,
        distance_from_viewer=distance,
        last_vouched_at=await _last_vouched_at(db, user),
    )


# ─────────────────────────────────────────────────────────────
# T3.18 — the public identity page
# ─────────────────────────────────────────────────────────────


async def _verified_at(db: AsyncSession, subject: User) -> datetime | None:
    """When the badge behind `highest_verification_level` was issued.

    Newest live badge of exactly that level: an older badge of a lower level
    says nothing about how fresh *this* claim is. Expired badges are excluded
    here for the same reason they no longer set the level at all (T_TRUST.1).
    """
    if subject.highest_verification_level is None:
        return None
    now = datetime.now(timezone.utc)
    return (
        await db.execute(
            select(func.max(VerificationBadge.verified_at)).where(
                VerificationBadge.subject_id == subject.id,
                VerificationBadge.level == subject.highest_verification_level,
                VerificationBadge.revoked_at.is_(None),
                or_(
                    VerificationBadge.expires_at.is_(None),
                    VerificationBadge.expires_at > now,
                ),
            )
        )
    ).scalar()


async def _last_vouched_at(db: AsyncSession, subject: User) -> datetime | None:
    """Date of the most recent live vouch pointing at this identity.

    The counter beside it ("3 people vouched") is silent about time, and three
    vouches from four years ago is a different statement from three from last
    month. One date is enough to tell those apart without listing the edges.
    """
    return (
        await db.execute(
            select(func.max(TrustEdge.created_at)).where(
                TrustEdge.to_user_id == subject.id,
                TrustEdge.kind == TrustEdgeKind.peer_verified,
                TrustEdge.revoked_at.is_(None),
            )
        )
    ).scalar()


class ArchiveRecord(BaseModel):
    """T3.19 — the historical record of an identity that can no longer act.

    Every field here is counted, never estimated. Losing the key took away the
    ability to sign; it took nothing away from what was already signed, and this
    is that — a museum placard, not a damaged profile.

    Two deliberate refusals:

    - **No percentages, no averages, no scores.** "99.98% success" reads as
      measured and is not; the honest counterpart is a count next to the total
      it was counted from, which is what `deals_closed` / `deals_total` and
      `routes_measured` / `routes_closed` are for.
    - **Distances are `straight_line`, in the field name and in the label.**
      `route_distance_km` is a great-circle arc: real tracks run 3–7% longer,
      and we are measuring where a parcel went, not what an aircraft flew.
      Calling it "kilometres travelled" would be a different number answering a
      different question.

    `capacity_kg` is the capacity carriers *declared* on completed trips, not
    weight delivered — we never weighed anything. The label must say so.
    """

    retired_at: datetime
    # Chain entries this identity authored, and how many carry a Nostr
    # signature. An unsigned entry is a real event in a real chain, but calling
    # it a signature would claim a proof that is not in the row.
    chain_entries: int
    signatures: int
    first_signature_at: datetime | None = None
    last_signature_at: datetime | None = None
    deals_total: int
    deals_closed: int
    # Closed deals whose route both endpoints of which are known airports, and
    # the total they came from. Publishing the sum without the denominator would
    # present a partial total as a complete one.
    routes_measured: int
    routes_closed: int
    straight_line_km: int | None = None
    # The record, not the average — in a museum the outlier is the exhibit.
    longest_hop_km: int | None = None
    longest_hop_route: str | None = None
    # T3.19 — the rarest route this identity used, and how many trips the whole
    # platform has on it. Rarity is a property of the map, not of the person,
    # and the label has to say so; the count travels with the corridor so the
    # claim cannot be read as bigger than it is.
    rarest_corridor: str | None = None
    rarest_corridor_trips: int | None = None
    trips_completed: int
    capacity_kg: float | None = None
    # T3.20 — the date the claim is allowed to reach, and no further. Anchors
    # publish a chain head to relays we do not control; everything beneath a
    # published head is fixed by someone else's timestamp, everything after it
    # is covered only by our own consistency check. So the sentence this feeds
    # is "independently checkable as of <date>" — never "verified forever", and
    # never a bare badge with no date at all. Null means no anchor exists yet,
    # in which case the card must claim nothing of the sort.
    last_anchor_at: datetime | None = None
    anchored_deals: int = 0


async def _archive_record(db: AsyncSession, subject: User) -> ArchiveRecord:
    """Count what this identity actually did. Two queries, no estimates."""
    rows = (
        await db.execute(
            select(
                Deal.status,
                Deal.carrier_id,
                Deal.trip_id,
                Trip.origin,
                Trip.destination,
                Trip.capacity,
            )
            .join(Trip, Trip.id == Deal.trip_id)
            .where(or_(Deal.sender_id == subject.id, Deal.carrier_id == subject.id))
        )
    ).all()

    deals_closed = 0
    routes_measured = 0
    total_km = 0.0
    longest_km: float | None = None
    longest_route: str | None = None
    carried_trips: dict[uuid.UUID, float] = {}

    corridors: set[tuple[str, str]] = set()

    for status, carrier_id, trip_id, origin, destination, capacity in rows:
        if status is not DealStatus.closed:
            continue
        deals_closed += 1
        corridors.add((origin, destination))
        if carrier_id == subject.id:
            # Per distinct trip: two parcels on one flight are one flight's
            # capacity, and adding it twice would invent a number.
            carried_trips[trip_id] = capacity or 0.0
        km = route_distance_km(origin, destination)
        if km is None:
            continue
        routes_measured += 1
        total_km += km
        if longest_km is None or km > longest_km:
            longest_km, longest_route = km, f"{origin}→{destination}"

    signed = DealEvent.nostr_sig.is_not(None)
    entries, signatures, first_sig, last_sig = (
        await db.execute(
            select(
                func.count(DealEvent.id),
                func.count(DealEvent.id).filter(signed),
                func.min(DealEvent.timestamp).filter(signed),
                func.max(DealEvent.timestamp).filter(signed),
            ).where(DealEvent.actor_id == subject.id)
        )
    ).one()

    # T3.19 — the rarest corridor this identity actually flew, measured the same
    # way `core/publish_filter.py` measures rarity: how many trips the whole
    # platform has on that route. One query for every corridor at once.
    #
    # Rarity is a property of the route, not of the person, and the label has to
    # say so — "flew where almost nobody flies" is a fact about the map. It is
    # here because in a museum the outlier is the exhibit, and a corridor two
    # people have ever used is more interesting than an average.
    rarest_corridor: str | None = None
    rarest_corridor_trips: int | None = None
    if corridors:
        counted = (
            await db.execute(
                select(Trip.origin, Trip.destination, func.count())
                .where(tuple_(Trip.origin, Trip.destination).in_(corridors))
                .group_by(Trip.origin, Trip.destination)
            )
        ).all()
        for origin, destination, seen in counted:
            if rarest_corridor_trips is None or seen < rarest_corridor_trips:
                rarest_corridor_trips = int(seen)
                rarest_corridor = f"{origin}→{destination}"

    # T3.20 — how far a third party can check this without taking our word.
    anchored_deals, last_anchor_at = (
        await db.execute(
            select(
                func.count(func.distinct(DealChainAnchor.deal_id)),
                func.max(DealChainAnchor.created_at),
            )
            .join(Deal, Deal.id == DealChainAnchor.deal_id)
            .where(or_(Deal.sender_id == subject.id, Deal.carrier_id == subject.id))
        )
    ).one()

    return ArchiveRecord(
        retired_at=subject.key_lost_at,
        chain_entries=entries or 0,
        signatures=signatures or 0,
        first_signature_at=first_sig,
        last_signature_at=last_sig,
        deals_total=len(rows),
        deals_closed=deals_closed,
        routes_measured=routes_measured,
        routes_closed=deals_closed,
        straight_line_km=round(total_km) if routes_measured else None,
        longest_hop_km=round(longest_km) if longest_km is not None else None,
        longest_hop_route=longest_route,
        rarest_corridor=rarest_corridor,
        rarest_corridor_trips=rarest_corridor_trips,
        trips_completed=len(carried_trips),
        capacity_kg=round(sum(carried_trips.values()), 1) if carried_trips else None,
        last_anchor_at=last_anchor_at,
        anchored_deals=anchored_deals or 0,
    )


class IdentityOut(BaseModel):
    """What a stranger may learn about an identity.

    Addressed by **npub**, not by the internal id: the key *is* the identity
    (`D-KEY-TIERS`), and the row id is an implementation detail that has no
    business in a shareable link.

    Never here, at any visibility level: email, phone, receiving addresses,
    anything from inside a vault. Those are not "private fields of a profile",
    they are a different category of data.
    """

    npub: str
    visibility: str
    display_name: str | None = None
    avatar_url: str | None = None
    member_since: datetime | None = None
    uba: int | None = None
    uba_level: str | None = None
    highest_verification_level: str | None = None
    # T_TRUST.1 — the date the level rests on, and the date of the most recent
    # vouch. A level or a counter with no date asserts more than the evidence:
    # "peer verified" reads as a present-tense fact, and the fact is that
    # somebody said so on a particular day (`D-EVIDENCE-DECAYS`).
    verified_at: datetime | None = None
    last_vouched_at: datetime | None = None
    verifications_issued_count: int | None = None
    verifications_received_count: int | None = None
    dealt_with_count: int | None = None
    key_lost: bool = False
    # T3.23 — a key swap is public information: everything signed before it
    # stays signed by a key this identity no longer holds, and a counterparty
    # weighing old evidence deserves the date rather than a surprise.
    identity_changed_at: datetime | None = None
    previous_npub: str | None = None
    # T3.19 — present only for a retired identity seen in full. Its absence on a
    # live one is not a missing field: there is no record to close while the key
    # still signs.
    archive: ArchiveRecord | None = None


@router.get("/identities/{npub}", response_model=IdentityOut)
async def public_identity(
    npub: str,
    viewer: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Open an identity by its key. No account required to look.

    A marketplace where nobody can look anybody up is a marketplace where
    nobody deals, so this is readable without signing in — and everything on it
    is already public elsewhere in the product. What is new is that it is in one
    place and has an address.
    """
    key = (npub or "").strip().lower()
    # T_KEYS.1 — check the shape before the database sees it. A key is 64
    # lowercase hex characters; anything else cannot match a row, so asking is
    # pointless — and one particular "anything else" was worse than pointless:
    # a NUL byte in the path reached asyncpg, which refuses it at the protocol
    # level (`invalid byte sequence for encoding "UTF8"`), turning a malformed
    # public URL into a 500. Found by the contract fuzzer, not by hand.
    #
    # 404 rather than 422, deliberately: this endpoint answers "no such
    # identity" to everything it will not talk about, and a distinct code for
    # "malformed" would be a second shape of answer on a public URL for no gain.
    if len(key) != 64 or not all(c in "0123456789abcdef" for c in key):
        raise HTTPException(status_code=404, detail="No such identity")
    subject = (
        await db.execute(select(User).where(User.nostr_pubkey == key))
    ).scalars().first()
    if subject is None:
        raise HTTPException(status_code=404, detail="No such identity")

    level = require_visible(subject, viewer)

    verified_at = await _verified_at(db, subject)

    if level == "minimal":
        # Existence and how well proven it is — enough to answer "is this key a
        # real participant" without drawing a portrait. The date comes along:
        # it is part of the claim, not part of the portrait, and "verified" with
        # no "when" is exactly the overstatement T_TRUST.1 exists to stop.
        return IdentityOut(
            npub=key,
            visibility=level,
            highest_verification_level=subject.highest_verification_level,
            verified_at=verified_at,
            key_lost=subject.key_lost,
        )

    uba = (
        int(subject.business_activity_level)
        if subject.business_activity_level is not None
        else None
    )
    return IdentityOut(
        npub=key,
        visibility=level,
        display_name=subject.display_name,
        avatar_url=get_presigned_url(subject.avatar_key) if subject.avatar_key else None,
        member_since=subject.created_at,
        uba=uba,
        uba_level=level_of(uba) if uba is not None else None,
        highest_verification_level=subject.highest_verification_level,
        verified_at=verified_at,
        last_vouched_at=await _last_vouched_at(db, subject),
        verifications_issued_count=subject.verifications_issued_count,
        verifications_received_count=subject.verifications_received_count,
        dealt_with_count=subject.dealt_with_count,
        key_lost=subject.key_lost,
        identity_changed_at=subject.identity_changed_at,
        previous_npub=subject.previous_nostr_pubkey,
        archive=await _archive_record(db, subject) if subject.key_lost else None,
    )
