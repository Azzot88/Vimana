"""T3.36–T3.39 — one endpoint for every card the two sides can raise.

Four groups of cards, one code path. What differs between "propose a pickup
point" and "report a problem" is entirely in `CATALOGUE`: who may create it, who
owes the answer, what evidence it needs, what accepting it changes. Writing four
modules would have meant writing the same four checks four times and letting
them drift.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.cards import (
    CANCELLABLE_STATUSES,
    CATALOGUE,
    PAYABLE_STATUSES,
    CardKind,
    CardSpec,
    addressed_role,
    resolve_ack_role,
    role_of,
)
from app.core.database import get_db
from app.core.deal_chain import append_deal_event, content_hash_of
from app.core.params import resolve_all
from app.core.signing import sign_vault_message
from app.core.trust import add_dealt_with, refresh_trust_counts
from app.models.deal import (
    Attachment, AttachmentKind, CardAckRole, CardState, Deal, DealEventType,
    DealStatus, DealVaultMessage,
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
    actor: User | None,
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

    `actor` is whoever's action caused the emission. T3.12.07 pt.2 — `None` when
    nobody's did: the delivery timer opening a dispute. The chain records an
    absent actor as absent (`deal_chain.compute_entry_hash`), which is truer
    than naming a party who pressed nothing.
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
        actor_id=actor.id if actor else None,
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
    from app.models.marketplace import Cargo

    terms = await _agreed_terms(db, deal.id)
    agreed = dict(terms.card_payload or {}) if terms else {}
    corridor = (agreed.get("normalized") or {}).get("direction")
    # T3.12.04 — the declared value is the cargo's; terms agreed before the cargo
    # left them still carry their own figure, and that one is what was accepted.
    declared = agreed.get("declared_value")
    if declared is None:
        cargo = await db.get(Cargo, deal.cargo_id)
        declared = cargo.declared_value if cargo else None
    return {
        "fixed_at": datetime.now(timezone.utc).isoformat(),
        "price_total": agreed.get("price_total"),
        "currency": agreed.get("currency"),
        "declared_value": declared,
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


#: T_UX.29 п.2 — the journey's own order, and the only three statuses that have
#: one. `delayed`, `customs` and `storage` are conditions rather than
#: milestones: each can genuinely come round twice, so they carry no rank and
#: are never refused for being «previous».
#:
#: Mirrored on the client by `lib/cardForms.TRANSIT_SEQUENCE`, which draws the
#: passed ones as a record and offers only what is still ahead. The pair a
#: reviewer compares is this dict and that list.
TRANSIT_ORDER: dict[str, int] = {"departed": 0, "layover": 1, "arrived": 2}

#: T_UX.28 п.6, kept — «Пересадка тоже может быть повторена несколько раз, но
#: строго до того как прилетел». A milestone that may be reached again: it holds
#: its place in the order without being spent by the first one.
TRANSIT_REPEATABLE: frozenset[str] = frozenset({"layover"})


async def _transit_stages(db: AsyncSession, deal_id: uuid.UUID) -> list[str]:
    """Which stages of the journey this deal has already been told about.

    T_UX.28 п.6. Read from the timeline rather than kept on the deal: the
    declarations are already there, and a column repeating them would be a
    second answer to «где посылка» that two writes could put at odds.
    """
    rows = (
        await db.execute(
            select(DealVaultMessage.card_payload)
            .where(
                DealVaultMessage.deal_id == deal_id,
                DealVaultMessage.card_kind == CardKind.transit_update.value,
            )
            .order_by(DealVaultMessage.created_at)
        )
    ).scalars().all()
    return [
        payload["stage"]
        for payload in rows
        if isinstance(payload, dict) and isinstance(payload.get("stage"), str)
    ]


async def _guard_transit_stage(
    db: AsyncSession, deal_id: uuid.UUID, stage: object
) -> None:
    """T_UX.28 п.6 (owner, 2026-09-19): «Если статус вылетел нажат, то его
    нельзя нажать во второй раз… Пересадка тоже может быть повторена несколько
    раз, но строго до того как прилетел. После прилёта Пересадка невозможна.»

    Two rules, and only two. Departure and arrival happen once each — a second
    «вылетел» is not new information, it is a contradiction of the first. A
    layover repeats freely, because a journey can have several, and stops being
    possible the moment the parcel has landed.

    Delay, customs and storage are deliberately unconstrained: each of them can
    genuinely happen again, and a rule forbidding the second one would silence
    the person carrying the parcel at the moment they have most to say.

    T_UX.29 п.2 (owner, 2026-09-20): «Если посылка уже отправлена и летит, то
    нельзя выбрать статус "Вылетела", она уже вылетела. И так со всеми статусами
    — не должно быть возможности выбрать предыдущий статус, только один из
    последующих.»

    The two rules above were three special cases, and they left every gap they
    did not name: a landed parcel could still be declared departed, because
    «departed already in done» was false for a deal whose carrier skipped it.
    `TRANSIT_ORDER` says the same thing once and closes all of them — nothing at
    or behind the furthest milestone already declared. The unranked three keep
    their freedom, which is the whole reason they are unranked.
    """
    if not isinstance(stage, str):
        return
    done = await _transit_stages(db, deal_id)
    rank = TRANSIT_ORDER.get(stage)
    if rank is None:
        return
    reached = max((TRANSIT_ORDER.get(s, -1) for s in done), default=-1)
    if rank < reached or (rank == reached and stage not in TRANSIT_REPEATABLE):
        raise HTTPException(
            status_code=409,
            detail=f"This deal is already past «{stage}»",
        )


async def _delivery_already_named(db: AsyncSession, deal: Deal) -> bool:
    """Whether anything has yet been said about where the parcel is handed over.

    T_UX.29 п.4 — the test behind «только Перевозчику». The rule is about the
    **first word**, not about who owns the subject: once the delivery has been
    named, everybody who may raise the card may propose a change to it, which is
    exactly what the recipient is meant to do with an arrangement that does not
    suit them.

    Any `dropoff.proposed` counts, unanswered ones included. A proposal still
    awaiting its «Принято» is a conversation that has been opened, and the
    answer to one the recipient disagrees with is a counter-proposal — which
    retires the first (`_supersede_open_proposal`), not a refusal followed by
    silence. Requiring an *accepted* card here would leave them able to decline
    and nothing else.

    The agreement counts too: `delivery_place` and `delivery_at` are sections the
    two sides negotiate, and a delivery named there is named. The method alone is
    not, deliberately — every agreement carries one, so counting it would mean
    the delivery was always already set and this rule would never fire once.

    Called by: `_raise_card`, for `dropoff.proposed`.
    """
    agreed = await _agreed_terms(db, deal.id)
    payload = (agreed.card_payload or {}) if agreed else {}
    if payload.get("delivery_place") or payload.get("delivery_at"):
        return True
    said = (
        await db.execute(
            select(func.count())
            .select_from(DealVaultMessage)
            .where(
                DealVaultMessage.deal_id == deal.id,
                DealVaultMessage.card_kind == CardKind.dropoff_proposed.value,
            )
        )
    ).scalar_one()
    return said > 0


async def _supersede_open_proposal(
    db: AsyncSession, deal_id: uuid.UUID, kind: CardKind
) -> uuid.UUID | None:
    """A newer proposal replaces an unanswered older one of the same kind.

    T_UX.29 п.7 (owner, 2026-09-20): «Вручение перенесено и подтверждено, но
    панель "Перенести вручение" всё ещё висит у второго участника.»

    Two people proposed a meeting within a minute of each other, one of the two
    was accepted, and the other stayed `pending` forever — a live «Принять ·
    Отклонить» over an arrangement that had already been settled by the card
    below it. Answering it would move the meeting back; ignoring it leaves the
    chat asking a question nobody should answer.

    Superseded rather than declined: nobody refused anything, the request was
    overtaken. That is what `CardState.superseded` means everywhere else in this
    protocol — see `_amend_meeting_point`, which retires an agreement the same
    way — and it keeps the older card readable in the chain with the newer one
    pointing back at it through `supersedes_id`.

    Only the meeting cards, on purpose. A second unanswered `handoff.declared`
    is not a correction of the first, it is a second account of the same act by
    a different person, and both belong in the record with their own photographs.

    Returns the id of the newest card it retired, for the new one to point at.

    Called by: `_raise_card`, for `pickup.proposed` and `dropoff.proposed`.
    """
    standing = (
        await db.execute(
            select(DealVaultMessage)
            .where(
                DealVaultMessage.deal_id == deal_id,
                DealVaultMessage.card_kind == kind.value,
                DealVaultMessage.card_state == CardState.pending,
            )
            .order_by(DealVaultMessage.created_at)
        )
    ).scalars().all()
    for row in standing:
        row.card_state = CardState.superseded
    return standing[-1].id if standing else None


async def _raise_card(
    deal_id: uuid.UUID,
    body: CardCreate,
    current_user: User,
    db: AsyncSession,
    *,
    has_files: bool = False,
) -> DealVaultMessage:
    """Every rule a card has to pass, and the row it becomes. **Does not commit.**

    T3.11.27 — split out of `create_card` so that raising a card *with its
    photograph* is one transaction rather than two requests. The caller decides
    when to commit; what must never happen is a committed card whose evidence
    was refused afterwards, because the vault is append-only and such a card can
    be neither confirmed nor withdrawn.

    Called by: `create_card`, `create_card_with_files`.
    """
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

    # T3.12.04 — the cargo is photographed at the response (owner, 2026-09-14),
    # while the deal can still be refused. A picture of «what I send» taken after
    # the carrier agreed would be evidence written after the fact, and the
    # handover has a photograph of its own.
    if kind is CardKind.cargo_photographed and deal.status not in (
        DealStatus.draft,
        DealStatus.matched,
    ):
        raise HTTPException(
            status_code=409,
            detail="The cargo is photographed at the response, before the terms are agreed",
        )

    # T3.35 — the fixation window closes when the flight leaves, whichever side
    # declares the handover: the rule is about the parcel and the clock, not
    # about who reached for the button.
    # T_UX.28 п.5 — one kind now, raised by whichever side is holding the
    # parcel. The rule is unchanged and was never about the role: the fixation
    # window closes when the flight leaves.
    if kind is CardKind.handoff_declared:
        await _guard_departure(db, deal, current_user)

    # T_UX.28 п.6 — the order of the journey's own statuses.
    if kind is CardKind.transit_update:
        await _guard_transit_stage(db, deal_id, body.payload.get("stage"))

    # T_UX.29 п.4 (owner, 2026-09-20): «Раздел "Способ передачи"… должен быть
    # доступен для настройки только Перевозчику, Получатель либо соглашается,
    # либо предлагает изменения.»
    #
    # The first word on how the parcel is handed over is the carrier's: they are
    # the one who will be standing there holding it, and an arrangement proposed
    # around them is a plan for somebody else's afternoon. Once there is one,
    # everybody who may raise the card gets it back — proposing a change to a
    # standing arrangement is precisely what the recipient is meant to do with
    # one that does not suit them.
    #
    # The screen narrows itself the same way. This is the rule (§6.9.5 п.6);
    # hiding the button is the courtesy.
    if (
        kind is CardKind.dropoff_proposed
        and creator is not CardAckRole.carrier
        and not await _delivery_already_named(db, deal)
    ):
        raise HTTPException(
            status_code=403,
            detail="The carrier sets the handover method — you may propose a change once it is set",
        )

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

    # T3.12.07 — on the receiving side, the person at the door declares. With a
    # separate recipient that is the recipient, not the sender who is elsewhere.
    if (
        kind is CardKind.delivery_declared
        and creator is CardAckRole.sender
        and deal.recipient_id is not None
        and deal.recipient_id != deal.sender_id
    ):
        raise HTTPException(
            status_code=403,
            detail="The recipient declares what they received",
        )

    if kind is CardKind.payment_declared:

        # T3.11.27 — «Деньги отдаются после получения груза: это и есть порядок,
        # который закрывает сделку» (owner, 2026-09-07).
        #
        # The order is the protection. Paid before the parcel arrives, the money
        # is gone and the leverage with it — and this platform moves no money of
        # its own until Фаза 4, so the sequence is the only thing standing
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
        # T3.12.05 — a sender who is also the recipient pays as the sender.
        expected = addressed_role(expected, deal)
        if creator is not expected:
            raise HTTPException(
                status_code=403,
                detail=f"The agreement says the {payer} pays",
            )

    if kind is CardKind.received_as_expected:
        # T3.12.08 — only a posted parcel is received this way: `posted`, or
        # `confirmed` when the carrier was paid first and the deal stayed open.
        if deal.status not in (DealStatus.posted, DealStatus.confirmed):
            raise HTTPException(
                status_code=409, detail="Nothing was posted to receive yet"
            )
        if (
            creator is CardAckRole.sender
            and deal.recipient_id is not None
            and deal.recipient_id != deal.sender_id
        ):
            raise HTTPException(
                status_code=403, detail="The recipient says what they received"
            )

    # T3.11.27 (owner, 2026-09-13) — **the last check before anything is
    # written, and the point of the whole endpoint split.**
    #
    # A declaration that stands on evidence cannot exist without it: the server
    # refuses to let the other side confirm one, and the vault is append-only,
    # so such a card can be neither answered nor withdrawn. Three photoless
    # «Отправлено по почте» cards in one chat is what that looks like.
    #
    # Checked here rather than at the top of the endpoint so every *semantic*
    # refusal keeps its own answer: a carrier declaring the sender's handover
    # still gets 403, a handover after departure still gets 409. «You sent this
    # the wrong way» is the least interesting thing that can be wrong with a
    # request, so it is the last thing said.
    if spec.requires_attachment is not None and not has_files:
        raise HTTPException(
            status_code=422,
            detail=(
                "This declaration is raised together with its photo — "
                "use /cards/with-files"
            ),
        )

    payload = _validate_payload(spec, body.payload)

    # T_UX.29 п.7 — a meeting proposed while another one is still unanswered
    # replaces it. Two live «Принять · Отклонить» over one meeting is two
    # answers to «где встречаемся», and the second one outlives the deal.
    overtaken = (
        await _supersede_open_proposal(db, deal_id, kind)
        if kind in (CardKind.pickup_proposed, CardKind.dropoff_proposed)
        else None
    )

    msg = DealVaultMessage(
        deal_id=deal_id,
        sender_id=current_user.id,
        text=body.text,
        is_system=True,
        card_kind=kind.value,
        card_payload=payload,
        card_state=CardState.pending if spec.ack_by else CardState.accepted,
        requires_ack_by=resolve_ack_role(spec, deal, creator),
        supersedes_id=overtaken,
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
    if kind is CardKind.received_as_expected:
        await _received_as_expected(db, deal, msg, current_user)
    return msg


async def _card_out(db: AsyncSession, msg_id: uuid.UUID) -> MessageOut:
    loaded = (
        await db.execute(
            select(DealVaultMessage)
            .where(DealVaultMessage.id == msg_id)
            .options(selectinload(DealVaultMessage.attachments))
        )
    ).scalar_one()
    from app.api.dealvault import _build_message_out

    return _build_message_out(loaded)


@router.post("/{deal_id}/cards", response_model=MessageOut, status_code=201)
async def create_card(
    deal_id: uuid.UUID,
    body: CardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Raise a card that needs no evidence.

    T3.11.27 (owner, 2026-09-13, after three photoless «Отправлено по почте»
    cards appeared in one chat): **a declaration that stands on evidence cannot
    be raised here at all.**

    It was a client convention before — `CardActions` sent such cards to
    `/cards/with-files` — and a convention is not a rule. An older bundle in
    somebody's browser, a retry from a stale tab, anything at all speaking this
    API, still produced the row this whole change exists to prevent: a
    declaration nobody can confirm, in a chain that cannot take it back. The
    refusal lives inside `_raise_card`, where it cannot be bypassed.
    """
    msg = await _raise_card(deal_id, body, current_user, db)
    await db.commit()
    return await _card_out(db, msg.id)


@router.post(
    "/{deal_id}/cards/with-files", response_model=MessageOut, status_code=201
)
async def create_card_with_files(
    deal_id: uuid.UUID,
    request: Request,
    files: list[UploadFile],
    # T_UX.28 п.4 (owner, 2026-09-19) — «селфи с отправителем, фото передачи,
    # фото отправки на почте и др.» A separate part rather than a flag on the
    # files above, because the two piles are filed under different kinds: one
    # shows what changed hands, the other who was standing there.
    selfies: list[UploadFile] = File(default=[]),
    kind: str = Form(...),
    payload: str = Form("{}"),
    text: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.11.27 — a declaration and its evidence, as one act (owner, 2026-09-12).

    «Фотография не прикладывается, а карточка в чате появляется без фото, это
    надо убрать. Без фото карточка в чат добавляться не должна.»

    Two requests could not give that. The client raised the card, then uploaded
    — and when the upload was refused (wrong type, too large, bytes that do not
    decode) the card was already committed to an append-only chain: a
    declaration nobody could confirm, because the server refuses an ack until
    the evidence is there, and nobody could withdraw either.

    So the order is inverted and the transaction is one. Every file is validated
    and stored **first**; only then is the card written; one commit covers the
    card, the attachments and both kinds of chain entry. A refusal costs the
    person a message on a form that is still open and their photographs still
    chosen.

    Several files, because a parcel has sides: «нужна возможность добавить
    несколько фото» — one photograph of a closed box proves the box existed.
    """
    from app.api.dealvault import attach_stored, store_upload

    if not files:
        raise HTTPException(status_code=422, detail="Attach at least one file")

    try:
        raw = json.loads(payload or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="payload is not valid JSON")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="payload must be an object")

    try:
        card_kind = CardKind(kind)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown card type")
    spec = CATALOGUE[card_kind]
    # T3.12.07 — required evidence, or evidence the card merely accepts.
    attachment_kind = spec.requires_attachment or spec.accepts_attachment
    if attachment_kind is None:
        raise HTTPException(
            status_code=422,
            detail="This card takes no attachments — raise it without files",
        )

    # Party and seal are checked before a byte is read: an outsider must not be
    # able to make us decode their images, and a sealed vault cannot take them.
    deal = await _deal_as_party(deal_id, current_user, db)
    if deal.sealed_at is not None:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")

    # The whole point of this endpoint, in three lines: accept the evidence,
    # then write the declaration.
    stored = [
        await store_upload(
            deal_id=deal_id,
            file=f,
            # T_UX.28 п.4 — a selfie is filed as a selfie. Same transaction,
            # same validation, different label: an arbiter reading the record
            # must be able to tell a photograph of the parcel from a photograph
            # of the two people who met over it.
            kind=(
                AttachmentKind.selfie.value
                if f in selfies
                else attachment_kind.value
            ),
            owner=current_user,
            db=db,
            # Content-Length covers the whole multipart body rather than one
            # part, so it is only an early «obviously too big» filter; each file
            # is still counted byte by byte while it is read.
            declared_length=request.headers.get("content-length"),
        )
        for f in [*files, *selfies]
    ]

    msg = await _raise_card(
        deal_id,
        CardCreate(kind=kind, payload=raw, text=text),
        current_user,
        db,
        has_files=True,
    )
    for item in stored:
        await attach_stored(
            stored=item,
            deal_id=deal_id,
            message_id=msg.id,
            actor=current_user,
            db=db,
        )
    await db.commit()
    return await _card_out(db, msg.id)


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


async def seal_closed_deal(db: AsyncSession, deal: Deal, actor: User) -> None:
    """T3.7 — a closed deal's vault stops taking new content.

    **Moved here from `deals.confirm_deal` (2026-09-12).** Sealing used to live
    inside that one endpoint, so the deal could close by the settlement pair —
    `payment.declared` accepted, status `confirmed` then `closed` — and the
    record would stay open for appends forever. Nobody noticed because the only
    close anybody had walked was the endpoint that also sealed. Closing is the
    event; sealing follows the close, wherever the close happens.

    The closing card goes in **first**, before the counts are taken: emitted
    after them it would be a message the seal's own tally does not include, and
    a record that miscounts itself by one is worse than one that simply stops.
    The seal event is appended before `sealed_at` is set, so the guard does not
    refuse its own seal.

    Idempotent by the `sealed_at` check: a second call is a no-op rather than a
    second tally, because two seals on one vault is two answers to «что в нём
    было».

    Called by: `apply_acceptance`, on the settlement pair that closes a deal.
    """
    if deal.sealed_at is not None:
        return

    await record_card(db, deal, CardKind.deal_sealed, actor)

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
        actor_id=actor.id,
        payload={"message_count": message_count, "file_count": file_count},
        author=actor,
    )
    deal.sealed_at = datetime.now(timezone.utc)

    # T2.4 — the trust edge belongs to the close, not to the endpoint that used
    # to own it. Two people who completed a deal have dealt with each other
    # whichever button finished it.
    await add_dealt_with(db, deal)
    await refresh_trust_counts(db, deal.sender_id)
    await refresh_trust_counts(db, deal.carrier_id)


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
    # T3.12.08 — where the deal stood before this answer moved it.
    previous = deal.status

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
            # T3.12.08 — paid while the parcel is in the post is «расчёт есть,
            # получения нет» (`IMPLEMENTATIONPLAN §3.12.5` п. 4): the deal stays
            # `confirmed`, unsealed and open to a dispute, until the receiving
            # side says it arrived as it should.
            if previous is not DealStatus.posted:
                await _close_deal(db, deal, card, actor)
        # T3.12.07 — the handover in hand is also the payment when the person
        # paying is the one receiving (`D-CARGO-MODEL` (5)): nothing is left to
        # settle, so the confirmation closes the deal on the same press.
        elif spec.kind is CardKind.delivery_declared and await _paid_at_the_door(
            db, deal, card
        ):
            deal.status = DealStatus.confirmed
            await db.flush()
            await append_deal_event(
                db,
                deal_id=deal.id,
                event_type=DealEventType.confirmed,
                actor_id=actor.id,
                payload={"card_kind": card.card_kind, "message_id": str(card.id)},
                author=actor,
            )
            await _close_deal(db, deal, card, actor)


async def _close_deal(
    db: AsyncSession, deal: Deal, card: DealVaultMessage, actor: User
) -> None:
    """`confirmed` → `closed`, in the chain, and the vault sealed.

    Called by: `apply_acceptance` — for `payment.declared`, and for a handover in
    hand that is also the payment.
    """
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
    # T3.7 — and the vault stops taking content. This used to happen only inside
    # `deals.confirm_deal`, so a deal closed by the pair stayed open for appends
    # forever (found 2026-09-12).
    await seal_closed_deal(db, deal, actor)


async def _received_as_expected(
    db: AsyncSession, deal: Deal, card: DealVaultMessage, actor: User
) -> None:
    """T3.12.08 — «получено как должно» ends a posted deal.

    Owner, 2026-09-14: the deal closes on whichever comes last, the confirmed
    payment or this card. Already paid (`confirmed`) — it closes and seals now.
    Not yet — the deal moves to `delivered`, and the payment confirmation closes
    it the way it closes any delivered deal. The carrier is never closed out of
    their money.

    Called by: `_raise_card`, after the card is written.
    """
    settled = deal.status is DealStatus.confirmed
    if not settled:
        deal.status = DealStatus.delivered
    await db.flush()
    await append_deal_event(
        db,
        deal_id=deal.id,
        event_type=DealEventType.received,
        actor_id=actor.id,
        payload={"card_kind": card.card_kind, "message_id": str(card.id)},
        author=actor,
    )
    if settled:
        await _close_deal(db, deal, card, actor)


async def _paid_at_the_door(
    db: AsyncSession, deal: Deal, card: DealVaultMessage
) -> bool:
    """T3.12.07 — does this handover settle the money as well?

    In hand, and the payer is the person receiving: the recipient when the
    agreement says the recipient pays, or the sender when they are the one at
    the door (no separate recipient, or «Получатель — я»). A sender paying for
    somebody else's parcel is not at the door — they settle remotely afterwards
    with `payment.declared` (`IMPLEMENTATIONPLAN §3.12.4` п. 4).
    """
    if (card.card_payload or {}).get("method", "in_person") != "in_person":
        return False
    agreed = await _agreed_terms(db, deal.id)
    payer = (agreed.card_payload or {}).get("payer", "sender") if agreed else "sender"
    if payer == "recipient":
        return True
    return deal.recipient_id is None or deal.recipient_id == deal.sender_id


async def record_card(
    db: AsyncSession,
    deal: Deal,
    kind: CardKind,
    actor: User | None,
    *,
    payload: dict | None = None,
) -> DealVaultMessage:
    """T3.39 — put a platform-side event into the vault as a card.

    Disputes and sealing are not raised through `POST /cards` and should not be:
    those endpoints do real work the card cannot carry — issuing an
    `ArbiterAccessGrant`, closing the hash chain. What they were missing is the
    other half: the deal's own record showed a status change with no card
    explaining it, so a party reading the chat saw the conversation stop.

    So the endpoints keep their machinery and call this to leave the card. The
    caller commits — the card belongs to the same transaction as the thing it
    records, or it is a note about something that may not have happened.
    """
    return await _emit(db, deal, kind, actor, payload=payload)
