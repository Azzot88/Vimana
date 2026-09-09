"""T3.34–T3.39 — the card catalogue, declared rather than coded.

Design note that outlives these tasks: the type of a card is a **field**, not a
prefix in the message text. T1.26 shipped `📍 SHARED ADDRESS` as a string the
frontend parsed back out; that worked for one card and does not survive thirty.

The second decision is this table. Groups 2–5 could each have been an endpoint
module — four files repeating the same four checks (is the caller a party, may
this role create this card, who owes the answer, what does accepting change).
Instead every card declares those four things here, and one generic endpoint
reads the declaration. A new card type is a row, not a module; the invariants of
§6.9.5 are enforced in one place rather than four.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from app.models.deal import AttachmentKind, CardAckRole, DealStatus

# Sentinel for "whoever did not create the card". Terms, handover conditions and
# cancellation all need it: the answer is always owed by the other side, and
# which side that is depends on who spoke first.
COUNTERPARTY = "counterparty"


class CardKind(str, enum.Enum):
    # Group 1 — terms (T3.35)
    terms_proposed = "terms.proposed"
    terms_countered = "terms.countered"
    terms_agreed = "terms.agreed"
    terms_declined = "terms.declined"
    terms_amended = "terms.amended"
    terms_reconfirm_requested = "terms.reconfirm_requested"

    # Group 2 — handover logistics (T3.36)
    handover_conditions = "handover.conditions"
    pickup_proposed = "pickup.proposed"
    pickup_confirmed = "pickup.confirmed"
    dropoff_proposed = "dropoff.proposed"
    dropoff_confirmed = "dropoff.confirmed"
    address_shared = "address.shared"
    route_note = "route.note"
    # T3.11.09 — the corridor checklist, anchored in the deal.
    #
    # Its own kind rather than `route.note` reused, which is what the task text
    # said. `route.note` is a badge — one word about a corridor — and an arbiter
    # reads these labels: filing a list of customs documents under «заметка о
    # маршруте» would mislabel the evidence at the moment it matters. The
    # instruction «новая сущность не заводится» is honoured: no table, no second
    # mechanism, one more member of a catalogue built to grow.
    compliance_checklist = "compliance.checklist"

    # Group 3 — custody (T3.37)
    handoff_declared = "handoff.declared"
    handoff_confirmed = "handoff.confirmed"
    transit_update = "transit.update"
    # T3.11.17 — the onward postal leg. 44.9 % of carriers post the parcel on
    # inside the destination country, so for half the deals the custody group
    # had a hole between «handed over» and «delivered».
    posted_declared = "posted.declared"
    posted_confirmed = "posted.confirmed"
    delivery_declared = "delivery.declared"
    delivery_confirmed = "delivery.confirmed"

    # Group 4 — settlement (T3.38; escrow parts land in Phase 5)
    payment_method_agreed = "payment.method_agreed"
    payment_declared = "payment.declared"
    payment_confirmed = "payment.confirmed"
    escrow_funded = "escrow.funded"
    collateral_posted = "collateral.posted"
    escrow_release_requested = "escrow.release_requested"
    escrow_released = "escrow.released"
    escrow_refunded = "escrow.refunded"

    # Group 5 — exceptions (T3.39)
    issue_reported = "issue.reported"
    cancel_requested = "cancel.requested"
    cancel_confirmed = "cancel.confirmed"
    dispute_opened = "dispute.opened"
    arbiter_joined = "arbiter.joined"
    dispute_resolved = "dispute.resolved"

    # Group 6 — closing
    deal_sealed = "deal.sealed"
    feedback_left = "feedback.left"

    # Group 7 — B2B (stream C, not before the first business contract)
    b2b_order_created = "b2b.order_created"
    b2b_leg_domestic = "b2b.leg_domestic"
    b2b_proof_of_delivery = "b2b.proof_of_delivery"


PARTIES = frozenset({CardAckRole.sender, CardAckRole.carrier})
ALL_PARTIES = PARTIES | {CardAckRole.recipient}

#: T3.11.27 — the statuses a cancellation may still touch, declared once.
#:
#: Owner's rule 2026-09-07: «Отмена до передачи должна подтверждаться обоими
#: участниками». After the handover the parcel exists somewhere and somebody is
#: carrying it; the question stops being «do we call this off» and becomes
#: «where is it», which is a dispute. A cancellation accepted mid-flight would
#: close a deal whose cargo is in the air, and leave the record saying nothing
#: was ever carried.
#:
#: Read by `api/cards.create_card` (refuses the request) and by
#: `tasks.cleanup.close_stale_cancellations` (lets a stale request lapse instead
#: of cancelling a deal that moved on while it waited). One tuple, because the
#: two of them disagreeing means the sweeper undoing a handover.
CANCELLABLE_STATUSES: tuple[DealStatus, ...] = (
    DealStatus.draft,
    DealStatus.matched,
    DealStatus.accepted,
)

#: T3.11.27 — the statuses in which the money may be declared.
#:
#: Owner's rule 2026-09-07: «Деньги отдаются после получения груза — это и есть
#: порядок, который закрывает сделку». The sequence is the protection: nothing
#: on this platform holds the money until Фаза 5, so «cargo first» is the only
#: thing between a sender and a stranger holding both their cash and their
#: parcel.
#:
#: `posted` is on the list beside `delivered`. The carrier's part ends at the
#: tracking code (`USERJOURNEY` Этап 4a), and making them wait for a postal
#: service would charge them for somebody else's schedule.
PAYABLE_STATUSES: tuple[DealStatus, ...] = (
    DealStatus.posted,
    DealStatus.delivered,
)


@dataclass(frozen=True)
class CardSpec:
    kind: CardKind
    group: str
    # Empty means the card is only ever produced by the server.
    creator_roles: frozenset = field(default_factory=frozenset)
    # A role, COUNTERPARTY, or None for an informational card nobody answers.
    ack_by: object | None = None
    # Enforced at creation: a declaration without its evidence is a claim.
    requires_attachment: AttachmentKind | None = None
    # Deal status reached when the card is accepted.
    on_accept_status: DealStatus | None = None
    # Card the server emits in reply to an acceptance, so that the record shows
    # both halves of a two-sided step rather than one card changing colour.
    on_accept_emit: CardKind | None = None
    implemented: bool = False


def _s(kind: CardKind, group: str, **kw) -> CardSpec:
    return CardSpec(kind=kind, group=group, **kw)


CATALOGUE: dict[CardKind, CardSpec] = {
    s.kind: s
    for s in (
        # ── group 1 · terms ────────────────────────────────────────────────
        # Created through `/terms`, which also normalises — hence not creatable
        # through the generic endpoint.
        _s(CardKind.terms_proposed, "terms", ack_by=COUNTERPARTY, implemented=True),
        _s(CardKind.terms_countered, "terms", ack_by=COUNTERPARTY, implemented=True),
        _s(CardKind.terms_agreed, "terms", implemented=True),
        _s(CardKind.terms_declined, "terms"),
        _s(CardKind.terms_amended, "terms", ack_by=COUNTERPARTY),
        _s(CardKind.terms_reconfirm_requested, "terms", ack_by=COUNTERPARTY, implemented=True),

        # ── group 2 · handover logistics ───────────────────────────────────
        _s(CardKind.handover_conditions, "logistics", creator_roles=PARTIES,
           ack_by=COUNTERPARTY, implemented=True),
        _s(CardKind.pickup_proposed, "logistics", creator_roles=PARTIES,
           ack_by=COUNTERPARTY, on_accept_emit=CardKind.pickup_confirmed,
           implemented=True),
        _s(CardKind.pickup_confirmed, "logistics", implemented=True),
        _s(CardKind.dropoff_proposed, "logistics", creator_roles=ALL_PARTIES,
           ack_by=COUNTERPARTY, on_accept_emit=CardKind.dropoff_confirmed,
           implemented=True),
        _s(CardKind.dropoff_confirmed, "logistics", implemented=True),
        _s(CardKind.address_shared, "logistics", implemented=True),
        _s(CardKind.route_note, "logistics"),
        # T3.11.09 — informational, and that is the decision, not an omission.
        # `D-COMPLIANCE-STANCE`: an unclosed item is visible to both sides and to
        # the arbiter, and that is enough — «вы знали» is proved by the record,
        # not by a refusal. `ack_by=None` is what «не блокирует сделку» looks
        # like in the catalogue.
        _s(CardKind.compliance_checklist, "logistics", creator_roles=PARTIES,
           implemented=True),

        # ── group 3 · custody ──────────────────────────────────────────────
        # The sender declares the handover and the carrier confirms taking it:
        # the cargo changes hands, so both hands have to say so.
        _s(CardKind.handoff_declared, "custody",
           creator_roles=frozenset({CardAckRole.sender}),
           ack_by=CardAckRole.carrier,
           requires_attachment=AttachmentKind.handoff_photo,
           on_accept_status=DealStatus.in_transit,
           on_accept_emit=CardKind.handoff_confirmed,
           implemented=True),
        _s(CardKind.handoff_confirmed, "custody", implemented=True),
        _s(CardKind.transit_update, "custody",
           creator_roles=frozenset({CardAckRole.carrier}), implemented=True),
        # T3.11.17 — «сдано в почту»: the photo is taken **before sealing**
        # (`USERJOURNEY` Этап 4a) and the tracking code is what ends the
        # carrier's part. Acked by the other side like every custody step, and
        # the status it reaches is `posted` rather than `delivered`: the parcel
        # is in the post, and calling that «delivered» would be the platform
        # saying something neither party said.
        _s(CardKind.posted_declared, "custody",
           creator_roles=frozenset({CardAckRole.carrier}),
           ack_by=COUNTERPARTY,
           requires_attachment=AttachmentKind.pre_seal_photo,
           on_accept_status=DealStatus.posted,
           on_accept_emit=CardKind.posted_confirmed,
           implemented=True),
        _s(CardKind.posted_confirmed, "custody", implemented=True),
        _s(CardKind.delivery_declared, "custody",
           creator_roles=frozenset({CardAckRole.carrier}),
           ack_by=COUNTERPARTY,  # resolved to recipient when there is one
           requires_attachment=AttachmentKind.receipt_photo,
           on_accept_status=DealStatus.delivered,
           on_accept_emit=CardKind.delivery_confirmed,
           implemented=True),
        _s(CardKind.delivery_confirmed, "custody", implemented=True),

        # ── group 4 · settlement ───────────────────────────────────────────
        _s(CardKind.payment_method_agreed, "settlement", creator_roles=PARTIES,
           ack_by=COUNTERPARTY, implemented=True),
        # The payer declares, the receiver of the money confirms. That second
        # card is what separates "said they paid" from "confirmed it arrived",
        # and the deal does not close without it — even in cash.
        # T3.11.27 — raised by **the payer**, who is named in the agreement
        # (owner's decision 2026-09-07): with a recipient who pays on delivery
        # it is not the sender. Both are listed here and the actual one is
        # resolved from the agreed card in `api.cards` — a static role cannot
        # know what two people wrote into their own terms.
        _s(CardKind.payment_declared, "settlement",
           creator_roles=frozenset({CardAckRole.sender, CardAckRole.recipient}),
           ack_by=CardAckRole.carrier,
           on_accept_status=DealStatus.confirmed,
           on_accept_emit=CardKind.payment_confirmed,
           implemented=True),
        _s(CardKind.payment_confirmed, "settlement", implemented=True),
        _s(CardKind.escrow_funded, "settlement"),
        _s(CardKind.collateral_posted, "settlement"),
        _s(CardKind.escrow_release_requested, "settlement"),
        _s(CardKind.escrow_released, "settlement"),
        _s(CardKind.escrow_refunded, "settlement"),

        # ── group 5 · exceptions ───────────────────────────────────────────
        _s(CardKind.issue_reported, "exceptions", creator_roles=ALL_PARTIES,
           implemented=True),
        # T3.11.27 — a cancellation is agreed by both, and reaches `cancelled`
        # rather than `closed`: a deal called off is not a deal completed, and
        # the record has to keep the two apart. Unanswered, it closes itself by
        # the timeout on the card (`tasks.cleanup.close_stale_cancellations`).
        _s(CardKind.cancel_requested, "exceptions", creator_roles=PARTIES,
           ack_by=COUNTERPARTY, on_accept_status=DealStatus.cancelled,
           on_accept_emit=CardKind.cancel_confirmed, implemented=True),
        _s(CardKind.cancel_confirmed, "exceptions", implemented=True),
        _s(CardKind.dispute_opened, "exceptions"),
        _s(CardKind.arbiter_joined, "exceptions"),
        _s(CardKind.dispute_resolved, "exceptions"),

        # ── group 6 · closing ──────────────────────────────────────────────
        _s(CardKind.deal_sealed, "closing"),
        _s(CardKind.feedback_left, "closing"),

        # ── group 7 · B2B ──────────────────────────────────────────────────
        _s(CardKind.b2b_order_created, "b2b"),
        _s(CardKind.b2b_leg_domestic, "b2b"),
        _s(CardKind.b2b_proof_of_delivery, "b2b"),
    )
}


def spec_for(kind: str) -> CardSpec | None:
    try:
        return CATALOGUE[CardKind(kind)]
    except ValueError:
        return None


def role_of(deal, user_id) -> CardAckRole | None:
    """Which side of this deal the user is on.

    Order matters: a deal where the sender is also the recipient answers
    `sender`, because that is the role that owes decisions.
    """
    if deal.sender_id == user_id:
        return CardAckRole.sender
    if deal.carrier_id == user_id:
        return CardAckRole.carrier
    if deal.recipient_id is not None and deal.recipient_id == user_id:
        return CardAckRole.recipient
    return None


def resolve_ack_role(spec: CardSpec, deal, creator: CardAckRole) -> CardAckRole | None:
    """Who owes the answer to this card.

    `COUNTERPARTY` is resolved here rather than stored, because it depends on
    who spoke. Delivery is the one asymmetric case: the person receiving the
    parcel confirms it, and that is the recipient when the deal has one and the
    sender when it does not — a deal with no separate recipient is one where the
    sender is both ends.
    """
    if spec.ack_by is None:
        return None
    if isinstance(spec.ack_by, CardAckRole):
        return spec.ack_by
    if spec.kind is CardKind.delivery_declared:
        return CardAckRole.recipient if deal.recipient_id else CardAckRole.sender
    return (
        CardAckRole.carrier if creator is CardAckRole.sender else CardAckRole.sender
    )


# ── T3.11.27 · the agreement in four sections ───────────────────────────────

#: The four parts of one deal card, in reading order. They exist so a change can
#: be announced by name — «изменены условия: Груз, Оплата» — and so the two ends
#: of the route stay distinguishable: editing the meeting place in Dubai must not
#: read as editing the delivery in New York (owner's decision 2026-09-07).
DEAL_SECTIONS: tuple[str, ...] = ("cargo", "handover", "delivery", "payment")

#: Which section each payload field belongs to. Fields absent from this map are
#: not part of the agreement people negotiate — `normalized` is computed,
#: `below_carrier_minimum` is a warning about a value already listed under
#: payment — and naming them in a change notice would report noise as news.
SECTION_OF: dict[str, str] = {
    "weight_kg": "cargo",
    "dimensions_cm": "cargo",
    "declared_value": "cargo",
    "cargo_what": "cargo",
    "cargo_packaging": "cargo",
    "cargo_fragile": "cargo",
    "cargo_open_on_handover": "cargo",
    "cargo_url": "cargo",
    "handover_method": "handover",
    "handover_place": "handover",
    "handover_at": "handover",
    "delivery_method": "delivery",
    "delivery_place": "delivery",
    "delivery_at": "delivery",
    "deadline": "delivery",
    "price_total": "payment",
    "currency": "payment",
    "payment_method": "payment",
    "payer": "payment",
}


def changed_sections(before: dict | None, after: dict) -> list[str]:
    """Which sections of the agreement this edit actually touched.

    Ordered by `DEAL_SECTIONS` rather than by dictionary order, so the notice
    reads the same way every time.

    A field the editor did not send is not a change: the client posts the whole
    card, and a missing optional value would otherwise look like somebody
    deleting a packaging note they never saw.

    Called by: `api.terms.propose_terms`.
    """
    if not before:
        return []
    touched = set()
    for field, section in SECTION_OF.items():
        if field not in after:
            continue
        if before.get(field) != after.get(field):
            touched.add(section)
    return [s for s in DEAL_SECTIONS if s in touched]
