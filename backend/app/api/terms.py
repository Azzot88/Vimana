"""T3.35 — the deal contract, as cards in the vault.

Two entry points converge on one card: the carrier's baseline lives in the trip
fields, the sender answers in the chat about that trip. Whoever proposes, the
server normalises the numbers the same way, so the two paths cannot disagree
about what was offered.

`terms.agreed` is the immutable snapshot everything later refers to. Nothing
edits it; a change is a new proposal that supersedes the old one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cards import CardKind, changed_sections, role_of
from app.core.database import get_db
from app.core.deal_chain import append_deal_event, content_hash_of
from app.core.params import resolve_all
from app.core.signing import sign_vault_message
from app.core.terms import below_carrier_minimum, normalize
from app.models.deal import (
    CardAckRole, CardState, Deal, DealEventType, DealStatus, DealVaultMessage,
)
from app.models.marketplace import Trip
from app.models.user import User
from app.schemas.terms import TermsIn, TermsOut

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
        raise HTTPException(status_code=409, detail="Deal is sealed")
    return deal


def _counterparty(deal: Deal, proposer: CardAckRole) -> CardAckRole:
    """Who owes the answer. A proposal answered by its own author is not an
    agreement, so this is never the proposer."""
    return CardAckRole.carrier if proposer is CardAckRole.sender else CardAckRole.sender


async def _build_payload(db: AsyncSession, trip: Trip, body: TermsIn) -> dict:
    normalized = await normalize(
        db,
        origin=trip.origin,
        destination=trip.destination,
        weight_kg=body.weight_kg,
        price_total=body.price_total,
        currency=body.currency,
        dimensions_cm=body.dimensions_cm,
    )
    return {
        "weight_kg": body.weight_kg,
        "dimensions_cm": body.dimensions_cm,
        "declared_value": body.declared_value,
        "price_total": body.price_total,
        "currency": body.currency,
        "deadline": body.deadline.isoformat() if body.deadline else None,
        "payment_method": body.payment_method,
        # T3.11.27 — the rest of the agreement. One card holds what four used to,
        # so that «договориться о передаче» stops being a step after both sides
        # have already agreed the deal.
        "cargo_what": body.cargo_what,
        "cargo_packaging": body.cargo_packaging,
        "cargo_fragile": body.cargo_fragile,
        "cargo_open_on_handover": body.cargo_open_on_handover,
        "cargo_url": body.cargo_url,
        "handover_method": body.handover_method,
        "handover_place": body.handover_place,
        "handover_at": body.handover_at.isoformat() if body.handover_at else None,
        "delivery_method": body.delivery_method,
        "delivery_place": body.delivery_place,
        "delivery_at": body.delivery_at.isoformat() if body.delivery_at else None,
        "payer": body.payer,
        "locked": body.locked,
        "normalized": normalized.as_dict(),
        "below_carrier_minimum": below_carrier_minimum(trip, body.price_total),
    }


#: T3.11.27 — how long an edit belongs to the person making it (owner's decision
#: 2026-09-07: «две минуты — это окно для правки, пока другой ждёт»). Long enough
#: to fix a price and a place in one go, short enough that a forgotten form does
#: not hold the deal: «если справился раньше — молодец, нет — запускай ещё раз».
EDIT_WINDOW = timedelta(minutes=2)

#: The cards the window applies to — the agreement and nothing else.
AGREEMENT_KINDS = frozenset(
    {CardKind.terms_proposed.value, CardKind.terms_countered.value}
)


def _hold_is_somebody_else_s(card: DealVaultMessage | None, actor: User) -> bool:
    """Is a pending card still inside somebody else's editing window?

    The window needs no column: a pending card carries who wrote it and when,
    which is the whole question. Storing a lock would add a second place where
    «who is editing» is recorded, and the two would disagree the first time a
    request failed halfway.

    Called by: `propose_terms`, `ack_terms`.
    """
    if card is None or card.card_state is not CardState.pending:
        return False
    # **Only the agreement.** The window exists so an edit is read finished
    # rather than mid-thought; every other card is a single act with nothing to
    # finish. Applied to all of them it would stop a carrier confirming a
    # handover for two minutes while both of them stand there holding the
    # parcel — a rule about typing, imposed on people meeting in a car park.
    if card.card_kind not in AGREEMENT_KINDS:
        return False
    if card.sender_id is None or card.sender_id == actor.id:
        return False
    written = card.created_at
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - written < EDIT_WINDOW


def _locked_against(payload: dict | None, editor: CardAckRole) -> list[str]:
    """Sections this editor may not touch.

    The carrier locks a section in **this** deal — stricter with one sender,
    softer with another (owner's decision 2026-09-07). Nobody else can lock
    anything: a lock is the carrier saying «I carry it this way or not at all»,
    and a sender who could lock a section would be dictating the terms of
    somebody else's flight.
    """
    if editor is CardAckRole.carrier:
        return []
    return list((payload or {}).get("locked") or [])


@router.post("/{deal_id}/terms", response_model=TermsOut, status_code=201)
async def propose_terms(
    deal_id: uuid.UUID,
    body: TermsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Propose, or counter an existing proposal.

    Countering supersedes rather than edits: the older card stays in the record
    with `superseded` on it, because "what was offered before" is exactly the
    question an arbiter asks.
    """
    deal = await _deal_as_party(deal_id, current_user, db)
    proposer = role_of(deal, current_user.id)
    if proposer is CardAckRole.recipient:
        raise HTTPException(
            status_code=403, detail="The recipient is not a party to the terms"
        )

    trip = (
        await db.execute(select(Trip).where(Trip.id == deal.trip_id))
    ).scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    superseded: DealVaultMessage | None = None
    if body.supersedes_id is not None:
        superseded = (
            await db.execute(
                select(DealVaultMessage).where(
                    DealVaultMessage.id == body.supersedes_id,
                    DealVaultMessage.deal_id == deal_id,
                )
            )
        ).scalar_one_or_none()
        if superseded is None:
            raise HTTPException(status_code=404, detail="Card to supersede not found")
        if superseded.card_state is not CardState.pending:
            raise HTTPException(
                status_code=409, detail="That proposal is no longer pending"
            )
        # T3.11.27 — the two-minute window. While it is open the card belongs to
        # whoever opened it: the other side neither edits nor confirms, so what
        # they read next is a finished change rather than somebody's second
        # thoughts. Refused rather than queued — «запускай ещё раз» is the
        # owner's own answer to being too slow.
        if _hold_is_somebody_else_s(superseded, current_user):
            raise HTTPException(
                status_code=409,
                detail="The other side is editing — try again in a moment",
            )
        # A locked section is the carrier's. Refused by name, so the sender is
        # told which part they may not touch rather than that the whole card is
        # closed to them.
        forbidden = _locked_against(superseded.card_payload, proposer)
        if forbidden:
            touched = changed_sections(
                superseded.card_payload, await _build_payload(db, trip, body)
            )
            clash = [s for s in touched if s in forbidden]
            if clash:
                raise HTTPException(
                    status_code=403,
                    detail=f"Locked by the carrier: {', '.join(clash)}",
                )

    payload = await _build_payload(db, trip, body)
    kind = CardKind.terms_countered if superseded else CardKind.terms_proposed

    msg = DealVaultMessage(
        deal_id=deal_id,
        sender_id=current_user.id,
        # The free-text part stays in the encrypted column, per §6.9.3.
        text=body.description,
        is_system=True,
        card_kind=kind.value,
        card_payload=payload,
        card_state=CardState.pending,
        requires_ack_by=_counterparty(deal, proposer),
        supersedes_id=superseded.id if superseded else None,
    )
    sign_vault_message(msg, current_user)
    db.add(msg)

    if superseded is not None:
        superseded.card_state = CardState.superseded

    await db.flush()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.message_added,
        actor_id=current_user.id,
        payload={
            "message_id": str(msg.id),
            "content_hash": content_hash_of(msg.text_ciphertext, msg.text_nonce),
            "msg_event_id": msg.nostr_event_id,
            "is_e2e": msg.is_e2e,
            "card_kind": kind.value,
            # T3.11.27 — which parts of the agreement this edit moved. In the
            # chain as well as in the chat: an arbiter reading the record a year
            # later needs to see that the price changed on the 12th, not to
            # diff two payloads themselves.
            "changed_sections": changed_sections(
                superseded.card_payload if superseded else None, payload
            ),
        },
        author=current_user,
    )

    # T3.11.27 — «в чате появляется сервисное сообщение: изменены условия
    # Доставки, или Оплаты, или всего вместе» (owner, 2026-09-07). A system line
    # rather than a silent card: the other side has to notice that what they
    # agreed to has moved, and a card that quietly changes colour is exactly how
    # somebody ends up carrying a parcel under terms they never read.
    touched = changed_sections(superseded.card_payload if superseded else None, payload)
    if touched:
        notice = DealVaultMessage(
            deal_id=deal_id,
            sender_id=None,
            text=None,
            is_system=True,
            card_kind=CardKind.terms_amended.value,
            card_payload={"sections": touched, "terms_id": str(msg.id)},
            card_state=CardState.accepted,
            requires_ack_by=None,
        )
        db.add(notice)
        await db.flush()
        await append_deal_event(
            db,
            deal_id=deal.id,
            event_type=DealEventType.message_added,
            actor_id=current_user.id,
            payload={
                "message_id": str(notice.id),
                "content_hash": content_hash_of(
                    notice.text_ciphertext, notice.text_nonce
                ),
                "card_kind": CardKind.terms_amended.value,
                "emitted_by_platform": True,
            },
            author=current_user,
        )

    await db.commit()
    await db.refresh(msg)
    return TermsOut.from_message(msg)


async def agree_from_proposal(
    db: AsyncSession, deal: Deal, proposal: DealVaultMessage, actor: User
) -> DealVaultMessage:
    """Turn an accepted proposal into the contract.

    Called from the generic ack path so that accepting terms and accepting any
    other card are the same gesture for the client. The snapshot copies the
    proposal's payload and stamps the parameter version in force — a rate
    changed tomorrow must not reach back into this deal (MASTERPLAN §4.1).
    """
    snapshot = dict(proposal.card_payload or {})
    snapshot["agreed_at"] = datetime.now(timezone.utc).isoformat()
    snapshot["proposal_id"] = str(proposal.id)
    corridor = (snapshot.get("normalized") or {}).get("direction")
    snapshot["platform_params"] = {
        key: str(value)
        for key, value in (await resolve_all(db, scope=corridor)).items()
    }

    agreed = DealVaultMessage(
        deal_id=deal.id,
        sender_id=None,
        text=proposal.text,
        is_system=True,
        card_kind=CardKind.terms_agreed.value,
        card_payload=snapshot,
        card_state=CardState.accepted,
        requires_ack_by=None,
        supersedes_id=proposal.id,
    )
    db.add(agreed)
    await db.flush()
    # The contract is the row an arbiter reads first — it belongs in the chain
    # for the same reason every other message does.
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.message_added,
        actor_id=actor.id,
        payload={
            "message_id": str(agreed.id),
            "content_hash": content_hash_of(agreed.text_ciphertext, agreed.text_nonce),
            "card_kind": CardKind.terms_agreed.value,
            "emitted_by_platform": True,
        },
        author=actor,
    )

    # The one place `accepted` is reached through a card. The legacy
    # `POST /deals/{id}/accept` still exists for the old UI; retiring it is a
    # follow-up, not a silent change of two paths into one.
    if deal.status in (DealStatus.draft, DealStatus.matched):
        deal.status = DealStatus.accepted

    await db.flush()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.accepted,
        actor_id=actor.id,
        payload={"card_kind": CardKind.terms_agreed.value, "message_id": str(agreed.id)},
        author=actor,
    )
    return agreed


@router.get("/{deal_id}/terms", response_model=TermsOut | None)
async def current_terms(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The contract in force, or the proposal still awaiting an answer."""
    deal = await _deal_as_party(deal_id, current_user, db)

    agreed = (
        await db.execute(
            select(DealVaultMessage)
            .where(
                DealVaultMessage.deal_id == deal.id,
                DealVaultMessage.card_kind == CardKind.terms_agreed.value,
            )
            .order_by(DealVaultMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if agreed is not None:
        return TermsOut.from_message(agreed)

    pending = (
        await db.execute(
            select(DealVaultMessage)
            .where(
                DealVaultMessage.deal_id == deal.id,
                DealVaultMessage.card_state == CardState.pending,
                DealVaultMessage.card_kind.in_(
                    [CardKind.terms_proposed.value, CardKind.terms_countered.value]
                ),
            )
            .order_by(DealVaultMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return TermsOut.from_message(pending) if pending else None
