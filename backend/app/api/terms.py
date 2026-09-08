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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cards import (
    CANCELLABLE_STATUSES,
    CardKind,
    changed_sections,
    role_of,
)
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

#: The cards an open editing window may hold. Only the agreement: while somebody
#: edits the terms, a handover confirmation between two people standing together
#: with a parcel has nothing to do with it and must not be refused.
AGREEMENT_KINDS = frozenset(
    {CardKind.terms_proposed.value, CardKind.terms_countered.value}
)



def _hold_is_somebody_else_s(deal: Deal, actor: User) -> bool:
    """Is somebody else in the middle of editing this deal's agreement?

    The hold lives on the deal, is taken before the change and released by it.
    An expired hold is simply not a hold — «запускай ещё раз» is the owner's own
    answer to being too slow, so nothing has to clear it.

    Called by: `propose_terms`, `take_edit_hold`, `api.dealvault.ack_card`.
    """
    if deal.edit_hold_by_id is None or deal.edit_hold_by_id == actor.id:
        return False
    until = deal.edit_hold_until
    if until is None:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until > datetime.now(timezone.utc)


def _release_hold(deal: Deal, actor: User) -> None:
    """A submitted change ends the window it was made in."""
    if deal.edit_hold_by_id == actor.id:
        deal.edit_hold_by_id = None
        deal.edit_hold_until = None


class EditHoldOut(BaseModel):
    """Until when the card is mine to change."""

    until: datetime


@router.post("/{deal_id}/terms/hold", response_model=EditHoldOut)
async def take_edit_hold(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.27 — «я сейчас правлю», for the next two minutes.

    Pressing «Редактировать» takes this before the form opens, so the other side
    reads a finished change rather than somebody's second thoughts — and so two
    people cannot answer each other's half-written versions in a loop.

    Re-taking my own hold extends it: a person still typing has not stopped
    editing, and making them lose the window mid-sentence would be a rule about
    typing speed.

    Nothing releases a stale hold and nothing needs to: two minutes after it was
    taken it stops being one, and the person who ran out «запускает ещё раз».
    """
    deal = await _deal_as_party(deal_id, current_user, db)
    if _hold_is_somebody_else_s(deal, current_user):
        raise HTTPException(
            status_code=409,
            detail="The other side is editing — try again in a moment",
        )
    deal.edit_hold_by_id = current_user.id
    deal.edit_hold_until = datetime.now(timezone.utc) + EDIT_WINDOW
    await db.commit()
    return EditHoldOut(until=deal.edit_hold_until)

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


#: T3.11.27 — the fields that stop being negotiable once the parcel has moved.
#:
#: The amount and the currency it is owed in, and nothing else. `payer` is not
#: here on purpose: who hands the money over is a practical arrangement two
#: people may still fix on the day, and it changes no number.
_PRICE_FIELDS: tuple[str, ...] = ("price_total", "currency")


async def _current_agreed(db: AsyncSession, deal_id: uuid.UUID) -> DealVaultMessage | None:
    """The contract in force. Latest `terms.agreed`, or None before there is one.

    Called by: `propose_terms`, to compare a new proposal against what stands.
    """
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


def _price_moved(agreed: dict | None, body: TermsIn) -> list[str]:
    """Which frozen fields this proposal would change.

    Compared as floats where both are numbers, so `100` and `100.0` are the same
    price: the client re-sends the whole card on every edit, and a proposal that
    kept the price would otherwise be refused for the shape of the number it
    came back as.
    """
    before = agreed or {}
    moved: list[str] = []
    for field in _PRICE_FIELDS:
        old = before.get(field)
        new = getattr(body, field, None)
        if old is None or new is None:
            continue
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            if float(old) != float(new):
                moved.append(field)
        elif old != new:
            moved.append(field)
    return moved


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

    # T3.11.27 — somebody else's editing window blocks the change itself, not
    # the proposal that came before it. Checked once, before anything is built:
    # the point of the window is that two people do not answer each other's
    # half-written versions in a loop.
    if _hold_is_somebody_else_s(deal, current_user):
        raise HTTPException(
            status_code=409,
            detail="The other side is editing — try again in a moment",
        )

    # T3.11.27 — «Цена не меняется на полпути» (owner, 2026-09-07).
    #
    # Once the parcel has changed hands the price is fixed (`MASTERPLAN §4.1`):
    # the carrier is already carrying it, and a new number now is not a
    # negotiation — it is one side changing the deal while holding the other
    # side's property. When circumstances really did change, the answer is a
    # linked deal with its own terms, which the owner deferred as rare and not
    # worth guessing the shape of.
    #
    # Refused by name rather than by closing the whole card: the rest of the
    # agreement still moves — a recipient who cannot come, a new address — and
    # freezing everything because one field is frozen would push those changes
    # back into the chat, where nothing confirms them.
    if deal.status not in CANCELLABLE_STATUSES:
        agreed = await _current_agreed(db, deal.id)
        if agreed is not None:
            frozen = _price_moved(agreed.card_payload, body)
            if frozen:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The price is fixed once the parcel has changed hands: "
                        f"{', '.join(frozen)}"
                    ),
                )

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

    # The change is made, so the window it was made in is over — «справился
    # раньше» is the ordinary case, and holding the deal until the two minutes
    # run out would punish being quick.
    _release_hold(deal, current_user)

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
