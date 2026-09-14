"""T3.3 / T3.12.05 — the recipient of a deal: an offer first, a role after.

Owner, 2026-09-13/14 (`D-CARGO-MODEL` (4), `IMPLEMENTATIONPLAN §3.12.3`): the
recipient is **offered** the role and takes it, and no right arrives before the
answer — the principle `T3.42` set for platform roles. Until now a link gave the
deal to whoever opened it, and a person picked from contacts was written in
already accepted: somebody could find themselves in a stranger's deal without
having said yes to anything («меня вписали в чужую сделку»).

A `DealParticipant` row is the offer, and once accepted the role:

- **pending** — nothing set; the person sees the offer and nothing of the deal;
- **accepted** — `accepted_at`; the person is `Deal.recipient_id` and reads the
  deal (`core.deal_access` counts only these rows);
- **declined** — by the person; with `refuse_future` it also sets
  `User.refuses_recipient_offers`, and later offers to them are refused;
- **revoked** — by the sender, or replaced by a newer offer.

Two ways to make an offer: a **link**, for somebody not on the platform, which
binds to whoever signs in with it; and a **person already here** — from friends,
or found by email, handle or key (owner, 2026-09-14). **One offer at a time**: a
new one withdraws the unanswered one, and while somebody holds the role no new
offer is made — the sender withdraws first.

One row per person per deal (`uq_participant_deal_user_role`): offering the same
person again reuses their row rather than adding one.

Functions (PROJECT §6.2a):
- `invite_recipient` — `POST /deals/{id}/invite-recipient`. Called by: `RecipientModal`.
- `offer_recipient` — `POST /deals/{id}/recipient-offers`. Called by: `RecipientModal`.
- `claim_invite` — `POST /deals/join/{token}`. Called by: `JoinDealPage`.
- `my_recipient_offers` — `GET /me/recipient-offers`. Called by: `RecipientOfferSection`.
- `accept_recipient_offer`, `decline_recipient_offer` —
  `POST /recipient-offers/{id}/accept|decline`. Called by: `JoinDealPage`,
  `RecipientOfferSection`.
- `withdraw_recipient` — `POST /deals/{id}/recipient/withdraw`. Called by: `RecipientModal`.
- `list_participants` — `GET /deals/{id}/participants`. Called by: `DealPage`, `RecipientModal`.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cargo import follow_recipient
from app.core.database import get_db
from app.core.deal_access import party_role
from app.models.deal import Deal, DealParticipant, DealParticipantRole, DealStatus
from app.models.marketplace import Cargo, Trip
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

#: A deal that is over has nobody left to hand the parcel to.
_FINISHED = (DealStatus.closed, DealStatus.cancelled)


class InviteOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    role: str
    invite_token: str
    invite_url: str  # convenience — the shareable URL
    invited_at: datetime


class ParticipantOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    user_id: uuid.UUID | None
    display_name: str | None
    npub: str | None
    role: str
    #: `pending` | `accepted` — the list never shows declined or revoked rows.
    state: str
    invited_at: datetime
    accepted_at: datetime | None


class OfferOut(BaseModel):
    """What a person sees of a deal they are offered: enough to decide, and
    nothing that belongs to the deal's participants — no chat, no terms."""

    id: uuid.UUID
    deal_id: uuid.UUID
    state: str
    route: str
    depart_at: datetime | None
    sender_name: str | None
    cargo_description: str | None
    invited_at: datetime


class RecipientBody(BaseModel):
    """A person already on the platform — by id (friends, search) or by key."""

    user_id: uuid.UUID | None = None
    npub: str | None = None


class DeclineBody(BaseModel):
    #: «Отказаться и больше не назначать меня» — also turns the account setting on.
    refuse_future: bool = False


def _invite_url(token: str) -> str:
    import os

    base = os.getenv("VIMANA_PUBLIC_URL", "https://vimana.dealvault.club")
    return f"{base}/join/deal/{token}"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _state(row: DealParticipant) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if row.declined_at is not None:
        return "declined"
    if row.accepted_at is not None:
        return "accepted"
    return "pending"


_PENDING = (
    DealParticipant.accepted_at.is_(None),
    DealParticipant.declined_at.is_(None),
    DealParticipant.revoked_at.is_(None),
)


async def _sender_deal(db: AsyncSession, deal_id: uuid.UUID, user: User) -> Deal:
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.sender_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the sender offers the recipient role"
        )
    return deal


def _can_offer(deal: Deal) -> None:
    if deal.status in _FINISHED:
        raise HTTPException(status_code=409, detail="The deal is over")
    if deal.recipient_id is not None:
        raise HTTPException(
            status_code=409,
            detail="The deal has a recipient — withdraw them before offering the role again",
        )


def _refuse_if_opted_out(person: User) -> None:
    if person.refuses_recipient_offers:
        raise HTTPException(
            status_code=403,
            detail="This person does not accept offers to be a recipient",
        )


async def _withdraw_pending(
    db: AsyncSession, deal_id: uuid.UUID, keep_id: uuid.UUID | None = None
) -> None:
    """One offer at a time: whatever was still unanswered is taken back."""
    stmt = (
        update(DealParticipant)
        .where(DealParticipant.deal_id == deal_id, *_PENDING)
        .values(revoked_at=_now())
        .execution_options(synchronize_session="fetch")
    )
    if keep_id is not None:
        stmt = stmt.where(DealParticipant.id != keep_id)
    await db.execute(stmt)


async def _route(db: AsyncSession, deal: Deal) -> tuple[str, datetime | None]:
    trip = await db.get(Trip, deal.trip_id)
    if trip is None:
        return "", None
    return f"{trip.origin} → {trip.destination}", trip.depart_at


async def _offer_view(db: AsyncSession, row: DealParticipant) -> OfferOut:
    deal = await db.get(Deal, row.deal_id)
    route, depart_at = await _route(db, deal) if deal else ("", None)
    cargo = await db.get(Cargo, deal.cargo_id) if deal else None
    sender = await db.get(User, deal.sender_id) if deal else None
    return OfferOut(
        id=row.id,
        deal_id=row.deal_id,
        state=_state(row),
        route=route,
        depart_at=depart_at,
        sender_name=sender.display_name if sender else None,
        cargo_description=cargo.description if cargo else None,
        invited_at=row.invited_at,
    )


def _notify(person: User, route: str, offered_by: str | None) -> None:
    """A letter, and the offer in the cabinet. The letter is a courtesy; the
    offer stands whether or not it is delivered."""
    try:
        from app.tasks.notifications import send_recipient_offered

        send_recipient_offered.delay(str(person.id), route, offered_by or "")
    except Exception:
        logger.exception("could not queue recipient-offer letter for %s", person.id)


async def _own_offer(
    db: AsyncSession, offer_id: uuid.UUID, user: User
) -> tuple[DealParticipant, Deal]:
    """An offer is answered only by the person it was made to. Somebody else's
    is not found rather than forbidden: its existence is not theirs to learn."""
    row = await db.get(DealParticipant, offer_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Offer not found")
    if _state(row) != "pending":
        raise HTTPException(status_code=409, detail="This offer is no longer open")
    deal = await db.get(Deal, row.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return row, deal


# ── making an offer ───────────────────────────────────────────────────────


@router.post("/deals/{deal_id}/invite-recipient", response_model=InviteOut, status_code=201)
async def invite_recipient(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A link, for a recipient who is not on the platform yet. It binds to
    whoever signs in with it, and that person still has to accept."""
    deal = await _sender_deal(db, deal_id, current_user)
    _can_offer(deal)
    await _withdraw_pending(db, deal_id)

    token = secrets.token_urlsafe(32)[:64]
    row = DealParticipant(
        deal_id=deal_id,
        user_id=None,
        role=DealParticipantRole.recipient,
        invited_by=current_user.id,
        invite_token=token,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return InviteOut(
        id=row.id,
        deal_id=row.deal_id,
        role=row.role.value,
        invite_token=token,
        invite_url=_invite_url(token),
        invited_at=row.invited_at,
    )


@router.post(
    "/deals/{deal_id}/recipient-offers", response_model=ParticipantOut, status_code=201
)
async def offer_recipient(
    deal_id: uuid.UUID,
    body: RecipientBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Offer the role to somebody already on the platform.

    A key that belongs to nobody is a `404` with a detail the form can show. It
    is not an invitation in disguise: the sender asked for *this* person.
    """
    if (body.user_id is None) == (body.npub is None):
        raise HTTPException(
            status_code=422, detail="Give exactly one of user_id or npub"
        )

    deal = await _sender_deal(db, deal_id, current_user)

    if body.user_id is not None:
        person = await db.get(User, body.user_id)
    else:
        person = (
            await db.execute(
                select(User).where(User.nostr_pubkey == body.npub.strip())
            )
        ).scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status_code=404, detail="No account for that person — send an invite link instead"
        )
    if person.id in (deal.sender_id, deal.carrier_id):
        raise HTTPException(
            status_code=400,
            detail="They are already a principal participant of this deal",
        )
    _refuse_if_opted_out(person)
    _can_offer(deal)

    row = (
        await db.execute(
            select(DealParticipant).where(
                DealParticipant.deal_id == deal_id,
                DealParticipant.user_id == person.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = DealParticipant(
            deal_id=deal_id,
            user_id=person.id,
            role=DealParticipantRole.recipient,
            invited_by=current_user.id,
        )
        db.add(row)
    else:
        row.accepted_at = None
        row.declined_at = None
        row.revoked_at = None
        row.invited_by = current_user.id
        row.invited_at = _now()
    await db.flush()
    await _withdraw_pending(db, deal_id, keep_id=row.id)

    route, _ = await _route(db, deal)
    await db.commit()
    await db.refresh(row)
    _notify(person, route, current_user.display_name)
    return ParticipantOut(
        id=row.id,
        deal_id=row.deal_id,
        user_id=row.user_id,
        display_name=person.display_name,
        npub=person.nostr_pubkey,
        role=row.role.value,
        state=_state(row),
        invited_at=row.invited_at,
        accepted_at=row.accepted_at,
    )


@router.post("/deals/join/{token}", response_model=OfferOut)
async def claim_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bind a link to the person who signed in with it — and nothing more.

    Opening the link used to be the acceptance. It is now the moment the offer
    finds its person: they see the route, the sender and what is being sent,
    and answer (owner, 2026-09-14). Idempotent for the same person.
    """
    row = (
        await db.execute(
            select(DealParticipant).where(DealParticipant.invite_token == token)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if row.revoked_at is not None:
        raise HTTPException(status_code=410, detail="This invite was withdrawn")
    if row.declined_at is not None:
        raise HTTPException(status_code=410, detail="This invite was declined")
    if row.user_id is not None and row.user_id != current_user.id:
        raise HTTPException(status_code=409, detail="Invite already claimed by another user")

    deal = await db.get(Deal, row.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id in (deal.sender_id, deal.carrier_id):
        raise HTTPException(
            status_code=400,
            detail="You are already a principal participant of this deal",
        )

    if row.user_id is None:
        _refuse_if_opted_out(current_user)
        # One row per person per deal: somebody offered this deal before (and
        # who declined, or whose offer was replaced) is offered again on their
        # own row, and the link row is folded into it.
        earlier = (
            await db.execute(
                select(DealParticipant).where(
                    DealParticipant.deal_id == row.deal_id,
                    DealParticipant.user_id == current_user.id,
                    DealParticipant.id != row.id,
                )
            )
        ).scalar_one_or_none()
        if earlier is not None:
            earlier.accepted_at = None
            earlier.declined_at = None
            earlier.revoked_at = None
            earlier.invited_by = row.invited_by
            earlier.invited_at = _now()
            row.revoked_at = _now()
            row = earlier
        else:
            row.user_id = current_user.id
        await db.commit()
        await db.refresh(row)
    return await _offer_view(db, row)


# ── answering it ──────────────────────────────────────────────────────────


@router.get("/me/recipient-offers", response_model=list[OfferOut])
async def my_recipient_offers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DealParticipant)
            .join(Deal, Deal.id == DealParticipant.deal_id)
            .where(
                DealParticipant.user_id == current_user.id,
                *_PENDING,
                Deal.status.notin_(_FINISHED),
            )
            .order_by(DealParticipant.invited_at.desc())
        )
    ).scalars().all()
    return [await _offer_view(db, row) for row in rows]


@router.post("/recipient-offers/{offer_id}/accept", response_model=OfferOut)
async def accept_recipient_offer(
    offer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row, deal = await _own_offer(db, offer_id, current_user)
    if deal.status in _FINISHED:
        raise HTTPException(status_code=409, detail="The deal is over")
    if deal.recipient_id is not None:
        raise HTTPException(status_code=409, detail="The deal already has a recipient")
    if current_user.id in (deal.sender_id, deal.carrier_id):
        raise HTTPException(
            status_code=400,
            detail="You are already a principal participant of this deal",
        )

    row.accepted_at = _now()
    deal.recipient_id = current_user.id
    # T3.12.03 — for a single deal its recipient is the cargo's final one.
    await follow_recipient(db, deal)
    await db.commit()
    await db.refresh(row)
    return await _offer_view(db, row)


@router.post("/recipient-offers/{offer_id}/decline", response_model=OfferOut)
async def decline_recipient_offer(
    offer_id: uuid.UUID,
    body: DeclineBody | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row, _ = await _own_offer(db, offer_id, current_user)
    row.declined_at = _now()
    if body is not None and body.refuse_future:
        current_user.refuses_recipient_offers = True
    await db.commit()
    await db.refresh(row)
    return await _offer_view(db, row)


@router.post("/deals/{deal_id}/recipient/self")
async def name_self_recipient(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.12.05 — «Получатель — я»: the sender takes the parcel at the other end.

    The one combination of places a person may hold in a deal (`D-CARGO-MODEL`
    (3)), and the one that needs no offer: nobody is being asked anything. The
    sender still reads the deal as the sender; cards addressed to the recipient
    go to them (`core.cards.addressed_role`).
    """
    deal = await _sender_deal(db, deal_id, current_user)
    _can_offer(deal)
    await _withdraw_pending(db, deal_id)
    deal.recipient_id = current_user.id
    await follow_recipient(db, deal)
    await db.commit()
    return {"recipient_id": str(current_user.id)}


# ── taking it back ────────────────────────────────────────────────────────


@router.post("/deals/{deal_id}/recipient/withdraw")
async def withdraw_recipient(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The sender takes back the open offer and the role, whichever there is.

    Past messages stay readable to the recipient (what reached them cannot be
    unsent); the deal, its list and its vault close to them from here on.
    """
    deal = await _sender_deal(db, deal_id, current_user)
    await db.execute(
        update(DealParticipant)
        .where(
            DealParticipant.deal_id == deal_id,
            DealParticipant.revoked_at.is_(None),
            DealParticipant.declined_at.is_(None),
        )
        .values(revoked_at=_now())
        .execution_options(synchronize_session="fetch")
    )
    if deal.recipient_id is not None:
        deal.recipient_id = None
        await follow_recipient(db, deal)
    await db.commit()
    return {"withdrawn": True}


@router.get("/deals/{deal_id}/participants", response_model=list[ParticipantOut])
async def list_participants(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The recipient and the open offer, for the deal's own people. Somebody
    merely offered the role is not one of them yet."""
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if await party_role(db, deal, current_user.id) is None:
        raise HTTPException(status_code=403, detail="Not a deal participant")

    rows = (
        await db.execute(
            select(DealParticipant, User)
            .join(User, DealParticipant.user_id == User.id, isouter=True)
            .where(
                DealParticipant.deal_id == deal_id,
                DealParticipant.revoked_at.is_(None),
                DealParticipant.declined_at.is_(None),
            )
        )
    ).all()
    return [
        ParticipantOut(
            id=p.id,
            deal_id=p.deal_id,
            user_id=p.user_id,
            display_name=(u.display_name if u else None),
            npub=(u.nostr_pubkey if u else None),
            role=p.role.value if hasattr(p.role, "value") else str(p.role),
            state=_state(p),
            invited_at=p.invited_at,
            accepted_at=p.accepted_at,
        )
        for (p, u) in rows
    ]
