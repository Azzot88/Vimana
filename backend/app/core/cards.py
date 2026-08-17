"""T3.34 — the card catalogue and what each kind is allowed to do.

Design note that outlives this task: the type of a card is a **field**, not a
prefix in the message text. T1.26 shipped `📍 SHARED ADDRESS` as a string the
frontend parsed back out; that worked for one card and does not survive thirty.

The catalogue below is the full list from IMPLEMENTATIONPLAN §6.9.4, declared in
one pass even though only part of it has behaviour yet. Declaring it whole is
deliberate: it keeps later tasks from inventing a second naming scheme, and
`implemented` says plainly which kinds a caller may actually create today.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models.deal import CardAckRole


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

    # Group 4 — settlement (T3.38, escrow parts in Phase 5)
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


@dataclass(frozen=True)
class CardSpec:
    kind: CardKind
    group: str
    # Who must answer. None = informational, nothing is owed.
    requires_ack_by: CardAckRole | None
    # False while the kind is declared but has no creation path yet.
    implemented: bool


def _spec(kind: CardKind, group: str, ack: CardAckRole | None = None, *, implemented: bool = False) -> CardSpec:
    return CardSpec(kind=kind, group=group, requires_ack_by=ack, implemented=implemented)


CATALOGUE: dict[CardKind, CardSpec] = {
    s.kind: s
    for s in (
        _spec(CardKind.terms_proposed, "terms"),
        _spec(CardKind.terms_countered, "terms"),
        _spec(CardKind.terms_agreed, "terms"),
        _spec(CardKind.terms_declined, "terms"),
        _spec(CardKind.terms_amended, "terms"),
        _spec(CardKind.terms_reconfirm_requested, "terms"),
        _spec(CardKind.handover_conditions, "logistics"),
        _spec(CardKind.pickup_proposed, "logistics"),
        _spec(CardKind.pickup_confirmed, "logistics"),
        _spec(CardKind.dropoff_proposed, "logistics"),
        _spec(CardKind.dropoff_confirmed, "logistics"),
        # The one kind that exists today: T1.26's shared address, now typed.
        # Informational — nobody owes an answer to an address.
        _spec(CardKind.address_shared, "logistics", None, implemented=True),
        _spec(CardKind.route_note, "logistics"),
        _spec(CardKind.handoff_declared, "custody", CardAckRole.carrier),
        _spec(CardKind.handoff_confirmed, "custody"),
        _spec(CardKind.transit_update, "custody"),
        _spec(CardKind.delivery_declared, "custody", CardAckRole.recipient),
        _spec(CardKind.delivery_confirmed, "custody"),
        _spec(CardKind.payment_method_agreed, "settlement"),
        _spec(CardKind.payment_declared, "settlement"),
        _spec(CardKind.payment_confirmed, "settlement"),
        _spec(CardKind.escrow_funded, "settlement"),
        _spec(CardKind.collateral_posted, "settlement"),
        _spec(CardKind.escrow_release_requested, "settlement"),
        _spec(CardKind.escrow_released, "settlement"),
        _spec(CardKind.escrow_refunded, "settlement"),
        _spec(CardKind.issue_reported, "exceptions"),
        _spec(CardKind.cancel_requested, "exceptions", CardAckRole.carrier),
        _spec(CardKind.cancel_confirmed, "exceptions"),
        _spec(CardKind.dispute_opened, "exceptions"),
        _spec(CardKind.arbiter_joined, "exceptions"),
        _spec(CardKind.dispute_resolved, "exceptions"),
        _spec(CardKind.deal_sealed, "closing"),
        _spec(CardKind.feedback_left, "closing"),
        _spec(CardKind.b2b_order_created, "b2b"),
        _spec(CardKind.b2b_leg_domestic, "b2b"),
        _spec(CardKind.b2b_proof_of_delivery, "b2b"),
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
