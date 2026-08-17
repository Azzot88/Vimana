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

    # Group 3 — custody (T3.37)
    handoff_declared = "handoff.declared"
    handoff_confirmed = "handoff.confirmed"
    transit_update = "transit.update"
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
        _s(CardKind.payment_declared, "settlement",
           creator_roles=frozenset({CardAckRole.sender}),
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
        _s(CardKind.cancel_requested, "exceptions", creator_roles=PARTIES,
           ack_by=COUNTERPARTY, on_accept_status=DealStatus.closed,
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
