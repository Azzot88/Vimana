"""T3.36–T3.39 — one endpoint for every card the two sides can raise.

Four groups of cards, one code path. What differs between "propose a pickup
point" and "report a problem" is entirely in `CATALOGUE`: who may create it, who
owes the answer, what evidence it needs, what accepting it changes. Writing four
modules would have meant writing the same four checks four times and letting
them drift.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.cards import CATALOGUE, CardKind, CardSpec, resolve_ack_role, role_of
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
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


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

    if spec.on_accept_status is not None:
        deal.status = spec.on_accept_status
        event = {
            DealStatus.in_transit: DealEventType.in_transit,
            DealStatus.delivered: DealEventType.received,
            DealStatus.confirmed: DealEventType.confirmed,
            DealStatus.closed: DealEventType.closed,
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
