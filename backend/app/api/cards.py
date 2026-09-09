"""T3.36–T3.39 — one endpoint for every card the two sides can raise.

Four groups of cards, one code path. What differs between "propose a pickup
point" and "report a problem" is entirely in `CATALOGUE`: who may create it, who
owes the answer, what evidence it needs, what accepting it changes. Writing four
modules would have meant writing the same four checks four times and letting
them drift.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.cards import (
    CANCELLABLE_STATUSES,
    CATALOGUE,
    PAYABLE_STATUSES,
    CardKind,
    CardSpec,
    resolve_ack_role,
    role_of,
)
from app.core.database import get_db
from app.core.deal_chain import append_deal_event, content_hash_of
from app.core.params import resolve_all
from app.core.signing import sign_vault_message
from app.models.deal import (
    CardAckRole, CardState, Deal, DealEventType, DealStatus, DealVaultMessage,
)
from app.models.marketplace import Trip
from app.models.user import User
from app.schemas.cards import PAYLOAD_MODELS, CardCreate
from app.schemas.dealvault import MessageOut

router = APIRouter()


async def _deal_as_party(deal_id: uuid.UUID, user: User, db: AsyncSession) -> Deal:
    deal = (
        await db.execute(select(Deal).where(Deal.id == deal_id))
    ).scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if role_of(deal, user.id) is None:
        raise HTTPException(status_code=403, detail="Not a party to this deal")
    if deal.sealed_at is not None:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")
    return deal


def _validate_payload(spec: CardSpec, raw: dict) -> dict:
    model = PAYLOAD_MODELS.get(spec.kind)
    if model is None:
        # A card with no declared shape takes no payload rather than any payload:
        # an unvalidated blob in the record is a blob an arbiter has to guess at.
        return {}
    try:
        return model(**raw).model_dump(mode="json")
    except ValidationError as exc:
        # T3.11.22 — `errors()` carries the original exception object under
        # `ctx` for anything raised by a custom validator, and FastAPI cannot
        # serialise that: the 422 became a 500 the moment a payload model grew
        # its first `model_validator`. `include_context=False` drops the object
        # and keeps the message, which is the part a client can act on.
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_context=False, include_url=False),
        ) from exc


async def _agreed_terms(db: AsyncSession, deal_id: uuid.UUID) -> DealVaultMessage | None:
    return (
        await db.execute(
            select(DealVaultMessage)
            .where(
                DealVaultMessage.deal_id == deal_id,
                DealVaultMessage.card_kind == CardKind.terms_agreed.value,
            )
            .order_by(DealVaultMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _emit(
    db: AsyncSession,
    deal: Deal,
    kind: CardKind,
    actor: User,
    *,
    payload: dict | None = None,
    supersedes: uuid.UUID | None = None,
) -> DealVaultMessage:
    """A server-authored card. `sender_id` stays NULL — nobody wrote it.

    **It is still chained.** T3.6 made the chain cover vault content, and a
    message with no chain entry is one that can be deleted or edited without the
    verifier noticing. Server-emitted cards are not a lesser kind of evidence —
    the fixation of price at handover and the sealing of the vault are among the
    most important rows in a deal — so they get the same `message_added` entry
    as anything a person typed.

    `actor` is whoever's action caused the emission. The chain has no notion of
    "the platform did it", and inventing a null actor would mean loosening a
    NOT NULL that exists to keep every entry attributable.
    """
    msg = DealVaultMessage(
        deal_id=deal.id,
        sender_id=None,
        text=None,
        is_system=True,
        card_kind=kind.value,
        card_payload=payload or {},
        card_state=CardState.accepted,
        requires_ack_by=None,
        supersedes_id=supersedes,
    )
    db.add(msg)
    await db.flush()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.message_added,
        actor_id=actor.id,
        payload={
            "message_id": str(msg.id),
            "content_hash": content_hash_of(msg.text_ciphertext, msg.text_nonce),
            "card_kind": kind.value,
            "emitted_by_platform": True,
        },
        author=actor,
    )
    return msg


async def _fixation_payload(db: AsyncSession, deal: Deal) -> dict:
    """What gets frozen when the cargo changes hands (MASTERPLAN §4.1).

    Price, declared value and the parameter version in force are copied out of
    the agreed terms at this moment and never re-read. A rate changed tomorrow
    must not reach back into a parcel already in the air.
    """
    terms = await _agreed_terms(db, deal.id)
    agreed = dict(terms.card_payload or {}) if terms else {}
    corridor = (agreed.get("normalized") or {}).get("direction")
    return {
        "fixed_at": datetime.now(timezone.utc).isoformat(),
        "price_total": agreed.get("price_total"),
        "currency": agreed.get("currency"),
        "declared_value": agreed.get("declared_value"),
        "terms_id": str(terms.id) if terms else None,
        "platform_params": {
            k: str(v) for k, v in (await resolve_all(db, scope=corridor)).items()
        },
    }


async def _cancel_deadline(db: AsyncSession, deal: Deal) -> datetime:
    """When an unanswered cancellation stops waiting.

    T3.11.27 — «по таймауту или по времени вылета», whichever comes first, and
    the timeout is **the shorter of the two accounts'** (owner's decision
    2026-09-07): whoever is in more of a hurry sets the pace, which is right for
    the side whose plans are burning.

    The flight caps it because after departure there is nothing left to cancel —
    the trip either took the parcel or it did not, and that is a different
    conversation from calling the deal off.

    Called by: `create_card`, for `cancel.requested`.
    """
    people = (
        (
            await db.execute(
                select(User.cancel_timeout_hours).where(
                    User.id.in_([deal.sender_id, deal.carrier_id])
                )
            )
        )
        .scalars()
        .all()
    )
    hours = min(people) if people else 48
    deadline = datetime.now(timezone.utc) + timedelta(hours=int(hours))

    trip = (
        await db.execute(select(Trip).where(Trip.id == deal.trip_id))
    ).scalar_one_or_none()
    if trip is not None and trip.depart_at is not None:
        depart = trip.depart_at
        if depart.tzinfo is None:
            depart = depart.replace(tzinfo=timezone.utc)
        deadline = min(deadline, depart)
    return deadline


async def _guard_departure(db: AsyncSession, deal: Deal, actor: User) -> None:
    """T3.35 / §6.9.4 — the fixation window closes when the flight leaves.

    Handing over after departure is not a late handover, it is a different trip.
    Rather than silently re-pricing, the deal gets a reconfirmation card and the
    declaration is refused: an automatic extension would quietly turn an agreed
    deal into another one at a week-old rate.
    """
    trip = (
        await db.execute(select(Trip).where(Trip.id == deal.trip_id))
    ).scalar_one_or_none()
    if trip is None or trip.depart_at is None:
        return
    depart = trip.depart_at
    if depart.tzinfo is None:
        depart = depart.replace(tzinfo=timezone.utc)
    if depart > datetime.now(timezone.utc):
        return

    existing = (
        await db.execute(
            select(DealVaultMessage).where(
                DealVaultMessage.deal_id == deal.id,
                DealVaultMessage.card_kind
                == CardKind.terms_reconfirm_requested.value,
                DealVaultMessage.card_state == CardState.pending,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        card = DealVaultMessage(
            deal_id=deal.id,
            sender_id=None,
            text=None,
            is_system=True,
            card_kind=CardKind.terms_reconfirm_requested.value,
            card_payload={"reason": "trip_departed", "depart_at": depart.isoformat()},
            card_state=CardState.pending,
            requires_ack_by=CardAckRole.sender,
        )
        db.add(card)
        await db.flush()
        await db.commit()

    raise HTTPException(
        status_code=409,
        detail="Trip has departed — terms need reconfirming before handover",
    )


@router.post("/{deal_id}/cards", response_model=MessageOut, status_code=201)
async def create_card(
    deal_id: uuid.UUID,
    body: CardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await _deal_as_party(deal_id, current_user, db)
    creator = role_of(deal, current_user.id)

    try:
        kind = CardKind(body.kind)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown card type")
    spec = CATALOGUE[kind]

    if not spec.creator_roles:
        raise HTTPException(
            status_code=403, detail="This card is only ever raised by the platform"
        )
    if creator not in spec.creator_roles:
        raise HTTPException(
            status_code=403, detail="Your role does not raise this card"
        )

    if kind is CardKind.handoff_declared:
        await _guard_departure(db, deal, current_user)

    # T3.11.27 — a cancellation is a thing you do *before* the parcel moves.
    # Owner's rule 2026-09-07: «Отмена до передачи должна подтверждаться обоими
    # участниками». Once it has changed hands the question is no longer «do we
    # call this off» but «where is it», and that is a dispute — a cancellation
    # accepted mid-flight would close a deal whose cargo is still in the air.
    #
    # It also carries its own deadline: unanswered, it closes itself «по
    # таймауту или по времени вылета», whichever comes first. Stamped onto the
    # card rather than computed when the sweeper runs, because both settings and
    # the flight can change afterwards, and a deadline that moved after it was
    # announced would be a promise the platform took back.
    if kind is CardKind.cancel_requested:
        if deal.status not in CANCELLABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="The parcel has already changed hands — open an issue instead",
            )
        payload = {
            **body.payload,
            "expires_at": (await _cancel_deadline(db, deal)).isoformat(),
        }
        body = CardCreate(kind=body.kind, payload=payload, text=body.text)

    # T3.11.27 — the money is declared by whoever the agreement says pays.
    # Read from the agreed card rather than from a role: «кто платит» is one of
    # the four sections the two of them negotiate, and with a recipient who pays
    # on delivery the sender is not the one settling. Defaults to the sender —
    # that is the field's own default and the shape of every deal written before
    # the section existed.
    # T3.11.18 — a buyout may only be asked of a carrier who offered it, and
    # never above the ceiling they named. Owner's rule 2026-09-08, and the whole
    # point of the two fields on the trip: the risk here is the **carrier's**
    # money, and a request that could exceed their own stated limit would put
    # the platform's logo on the scheme the market dump describes.
    #
    # Read from the trip rather than the agreement: this is the carrier's
    # standing offer, not something the two of them negotiated, and a sender who
    # talked the ceiling up in chat has not moved it.
    if kind is CardKind.buyout_requested:
        trip = (
            await db.execute(select(Trip).where(Trip.id == deal.trip_id))
        ).scalar_one_or_none()
        offers = "purchase_on_request" in ((trip.services if trip else None) or [])
        if not offers:
            raise HTTPException(
                status_code=409,
                detail="This carrier does not buy goods to order",
            )
        ceiling = trip.buyout_limit if trip else None
        asked = float(body.payload.get("max_total") or 0)
        if ceiling is not None and asked > ceiling:
            raise HTTPException(
                status_code=409,
                detail=f"Above this carrier's buyout limit ({ceiling})",
            )

    if kind is CardKind.payment_declared:

        # T3.11.27 — «Деньги отдаются после получения груза: это и есть порядок,
        # который закрывает сделку» (owner, 2026-09-07).
        #
        # The order is the protection. Paid before the parcel arrives, the money
        # is gone and the leverage with it — and this platform moves no money of
        # its own until Фаза 5, so the sequence is the only thing standing
        # between a sender and a stranger with their cash and their cargo.
        #
        # `posted` counts: the carrier's part ends at the tracking code
        # (`USERJOURNEY` Этап 4a), and holding their payment for a postal service's
        # schedule would charge them for somebody else's pace.
        if deal.status not in PAYABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="The money is settled after the parcel arrives, not before",
            )
        agreed = await _agreed_terms(db, deal.id)
        payer = (agreed.card_payload or {}).get("payer", "sender") if agreed else "sender"
        expected = (
            CardAckRole.recipient if payer == "recipient" else CardAckRole.sender
        )
        if creator is not expected:
            raise HTTPException(
                status_code=403,
                detail=f"The agreement says the {payer} pays",
            )

    payload = _validate_payload(spec, body.payload)

    msg = DealVaultMessage(
        deal_id=deal_id,
        sender_id=current_user.id,
        text=body.text,
        is_system=True,
        card_kind=kind.value,
        card_payload=payload,
        card_state=CardState.pending if spec.ack_by else CardState.accepted,
        requires_ack_by=resolve_ack_role(spec, deal, creator),
    )
    sign_vault_message(msg, current_user)
    db.add(msg)
    await db.flush()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.message_added,
        actor_id=current_user.id,
        payload={
            "message_id": str(msg.id),
            # Without the hash the entry points at a row but proves nothing
            # about its contents — `verify_content` reports the gap as a
            # mismatch, which is exactly what it is.
            "content_hash": content_hash_of(msg.text_ciphertext, msg.text_nonce),
            "msg_event_id": msg.nostr_event_id,
            "is_e2e": msg.is_e2e,
            "card_kind": kind.value,
        },
        author=current_user,
    )
    await db.commit()

    loaded = (
        await db.execute(
            select(DealVaultMessage)
            .where(DealVaultMessage.id == msg.id)
            .options(selectinload(DealVaultMessage.attachments))
        )
    ).scalar_one()
    from app.api.dealvault import _build_message_out

    return _build_message_out(loaded)


#: T3.11.27 — which end of the route a meeting-point card is about, and which
#: fields of the agreement it writes. `pickup` is the handover in the departure
#: city, `dropoff` the delivery in the arrival one; they were deliberately kept
#: apart so «перенесли встречу в Дубае» never reads as «перенесли вручение в
#: Нью-Йорке».
_MEETING_SECTION: dict[CardKind, str] = {
    CardKind.pickup_proposed: "handover",
    CardKind.dropoff_proposed: "delivery",
}


async def _amend_meeting_point(
    db: AsyncSession, deal: Deal, card: DealVaultMessage, actor: User
) -> None:
    """Write an agreed meeting point back into the agreement.

    T3.11.27, owner's rule 2026-09-07: «Место встречи меняется отдельно» — время
    переносят чаще всего, и ради этого не должна пересогласовываться вся
    карточка. **Но подтверждение второй стороны нужно и здесь**, which is what
    `pickup.proposed` / `dropoff.proposed` already are: one side names a place,
    the other accepts it. What was missing is this half — the agreement kept
    showing the old address, so the card and the chat disagreed about where two
    people were meeting tomorrow.

    Superseded rather than edited in place. `CardState.superseded` is how a
    correction looks in this protocol (a card is never edited), and the agreed
    contract is the last row that should quietly change under a reader: a party
    who scrolls back has to find the version they answered, still saying what it
    said. Only the one section moves; the price, the cargo and the payer come
    across untouched, so nobody re-agrees a price to move a meeting by an hour.

    Called by: `apply_acceptance`, for the two meeting-point cards.
    """
    section = _MEETING_SECTION.get(CardKind(card.card_kind))
    if section is None:
        return
    agreed = await _agreed_terms(db, deal.id)
    if agreed is None:
        # Nothing agreed yet — the meeting point *is* the news, and there is no
        # contract for it to contradict.
        return

    proposal = card.card_payload or {}
    moved = {
        f"{section}_method": proposal.get("method"),
        f"{section}_place": proposal.get("city"),
        f"{section}_at": proposal.get("at"),
    }
    # A field the proposal did not carry is not an erasure: `MeetingPoint` makes
    # everything but the method optional, and a card that named only a new time
    # must not blank the address it was agreed at.
    moved = {k: v for k, v in moved.items() if v is not None}
    if not moved:
        return

    payload = {**(agreed.card_payload or {}), **moved}
    if payload == agreed.card_payload:
        return

    amended = DealVaultMessage(
        deal_id=deal.id,
        sender_id=None,
        text=None,
        is_system=True,
        card_kind=CardKind.terms_agreed.value,
        card_payload=payload,
        card_state=CardState.accepted,
        requires_ack_by=None,
        supersedes_id=agreed.id,
    )
    db.add(amended)
    agreed.card_state = CardState.superseded
    await db.flush()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.message_added,
        actor_id=actor.id,
        payload={
            "message_id": str(amended.id),
            "content_hash": content_hash_of(None, None),
            "card_kind": CardKind.terms_agreed.value,
            # Named the same way `propose_terms` names it, so an arbiter reading
            # the chain sees one vocabulary for "the agreement moved" whether it
            # moved through the form or through a meeting-point card.
            "changed_sections": [section],
            "amended_by": str(card.id),
        },
        author=actor,
    )


async def apply_acceptance(
    db: AsyncSession, deal: Deal, card: DealVaultMessage, actor: User
) -> None:
    """What accepting a card changes, per its declaration.

    Called from the single ack path so that every two-sided step behaves the
    same way: the answer is recorded, the paired card is emitted so the record
    shows both halves, and the deal status moves only here.
    """
    spec = CATALOGUE.get(CardKind(card.card_kind))
    if spec is None:
        return

    if spec.requires_attachment is not None:
        has_evidence = any(
            a.kind is spec.requires_attachment for a in (card.attachments or [])
        )
        if not has_evidence:
            raise HTTPException(
                status_code=422,
                detail="This declaration has no photo attached yet",
            )

    if spec.on_accept_emit is not None:
        payload: dict | None = None
        if spec.on_accept_emit is CardKind.handoff_confirmed:
            payload = await _fixation_payload(db, deal)
        await _emit(
            db, deal, spec.on_accept_emit, actor, payload=payload, supersedes=card.id
        )

    # T3.11.27 — an agreed meeting point moves the agreement, not only the chat.
    await _amend_meeting_point(db, deal, card, actor)

    if spec.on_accept_status is not None:
        deal.status = spec.on_accept_status
        event = {
            DealStatus.in_transit: DealEventType.in_transit,
            DealStatus.posted: DealEventType.posted,
            DealStatus.delivered: DealEventType.received,
            DealStatus.confirmed: DealEventType.confirmed,
            DealStatus.closed: DealEventType.closed,
            DealStatus.cancelled: DealEventType.cancelled,
        }.get(spec.on_accept_status)
        if event is not None:
            await db.flush()
            await append_deal_event(
                db,
                deal_id=deal.id,
                event_type=event,
                actor_id=actor.id,
                payload={"card_kind": card.card_kind, "message_id": str(card.id)},
                author=actor,
            )

        # T3.11.27 — the settled money closes the deal. Owner's rule 2026-09-07:
        # «нажать кнопку "Оплата произведена", вторая сторона подтверждает такой
        # же кнопкой, действие отображается в чате и сделка закрывается».
        #
        # Two entries rather than one status jumped over: `confirmed` is «the
        # money is confirmed» and `closed` is «there is nothing left to do», and
        # a record that shows the second without the first cannot answer when
        # the payment was agreed.
        if spec.on_accept_status is DealStatus.confirmed:
            deal.status = DealStatus.closed
            await db.flush()
            await append_deal_event(
                db,
                deal_id=deal.id,
                event_type=DealEventType.closed,
                actor_id=actor.id,
                payload={"card_kind": card.card_kind, "message_id": str(card.id)},
                author=actor,
            )


async def record_card(
    db: AsyncSession,
    deal: Deal,
    kind: CardKind,
    actor: User,
    *,
    payload: dict | None = None,
) -> DealVaultMessage:
    """T3.39 — put a platform-side event into the vault as a card.

    Disputes and sealing are not raised through `POST /cards` and should not be:
    those endpoints do real work the card cannot carry — issuing an
    `OperatorAccessGrant`, closing the hash chain. What they were missing is the
    other half: the deal's own record showed a status change with no card
    explaining it, so a party reading the chat saw the conversation stop.

    So the endpoints keep their machinery and call this to leave the card. The
    caller commits — the card belongs to the same transaction as the thing it
    records, or it is a note about something that may not have happened.
    """
    return await _emit(db, deal, kind, actor, payload=payload)
