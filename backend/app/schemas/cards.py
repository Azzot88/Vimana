"""T3.36–T3.39 — payload shapes, one per card kind.

Every model here holds only what the server must be able to read: enumerations,
amounts, dates. Free text and addresses travel in the message's encrypted `text`
column (§6.9.3), which is why none of these models has a `description` field
even where the card obviously has something to say.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

from app.core.cards import CardKind

#: T3.11.22 — **the** list of handover methods, declared once.
#:
#: It lived here and, word for word, in `schemas/marketplace.py`: two literal
#: lists obliged to agree forever and connected by nothing. They would have
#: diverged in silence, and the place it became visible is the worst one — a
#: deal card unable to name the method the trip was published with, which is
#: exactly the moment the parcel changes hands.
#:
#: This file owns it because the deal card is where the method is *executed*;
#: the trip merely offers it. `schemas/marketplace` imports the tuple below
#: rather than re-typing the words. The earlier comment there said the
#: duplication avoided a marketplace→cards dependency — that dependency does not
#: exist (nothing in `cards` imports `marketplace`), and avoiding it bought a
#: second copy of the vocabulary.
HandoverMethod = Literal[
    "in_person", "local_post", "courier", "parcel_locker", "poste_restante"
]

#: The same vocabulary at runtime, for validators that check membership rather
#: than annotate a field. Derived from the `Literal` so the two cannot drift:
#: adding a method means editing one line above and nothing else.
HANDOVER_METHODS: frozenset[str] = frozenset(get_args(HandoverMethod))


class HandoverConditions(BaseModel):
    packaging: str | None = Field(default=None, max_length=200)
    open_on_handover: bool = False
    photo_required: bool = True
    fragile: bool = False
    temperature_note: str | None = Field(default=None, max_length=200)


class MeetingPoint(BaseModel):
    """Shared by pickup and dropoff — the shape of "where and when" does not
    change depending on which end of the route it describes."""

    method: HandoverMethod
    city: str | None = Field(default=None, max_length=120)
    at: datetime | None = None
    window_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    tracking_number: str | None = Field(default=None, max_length=64)
    # T3.11.22 — **which** company actually took it, beside the number they gave.
    # The trip says what the carrier can do («CDEK is the one near me»); the card
    # says what happened («posted with CDEK, here is the code»). A tracking
    # number without the company that issued it is a string nobody can follow —
    # the two belong on the same card and always did.
    #
    # Free text, like the trip's list and for the same reason: the catalogue has
    # no external source and must not be able to tell somebody the company that
    # took their parcel does not exist.
    postal_service: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _service_needs_a_carrier_of_parcels(self) -> "MeetingPoint":
        """T3.11.22 — the same narrowing as on the trip, one step further in.

        A company name on a hand-to-hand meeting is a contradiction: nothing was
        posted, so nobody carried it. Refused rather than ignored — a field
        quietly dropped is a field the sender believes they filled in.
        """
        if self.postal_service and self.method not in ("local_post", "courier"):
            raise ValueError(
                "postal_service only applies to local_post or courier"
            )
        return self


class HandoffDeclared(BaseModel):
    # Nothing required: the evidence is the photo, checked at acceptance.
    parcel_count: int = Field(default=1, ge=1, le=20)


class TransitUpdate(BaseModel):
    stage: Literal["departed", "arrived", "delayed", "customs"]
    eta: datetime | None = None


class DeliveryDeclared(BaseModel):
    method: HandoverMethod = "in_person"


class PaymentMethodAgreed(BaseModel):
    method: Literal["cash", "platform", "escrow"]


class PaymentDeclared(BaseModel):
    amount: float = Field(gt=0)
    # T3.11.07 — four characters: `USDT` and `USDC` are four, and a payment is
    # declared in the currency the deal was agreed in.
    currency: str = Field(default="USD", min_length=3, max_length=4)
    method: Literal["cash", "platform", "escrow"] = "cash"


class IssueReported(BaseModel):
    category: Literal["delay", "damage", "unreachable", "mismatch"]


class CancelRequested(BaseModel):
    # Who eats the costs already incurred. Named at request time, because the
    # question surfaces anyway and answering it later means answering it in a
    # dispute.
    costs_borne_by: Literal["sender", "carrier", "split", "none"] = "none"


PAYLOAD_MODELS: dict[CardKind, type[BaseModel]] = {
    CardKind.handover_conditions: HandoverConditions,
    CardKind.pickup_proposed: MeetingPoint,
    CardKind.dropoff_proposed: MeetingPoint,
    CardKind.handoff_declared: HandoffDeclared,
    CardKind.transit_update: TransitUpdate,
    CardKind.delivery_declared: DeliveryDeclared,
    CardKind.payment_method_agreed: PaymentMethodAgreed,
    CardKind.payment_declared: PaymentDeclared,
    CardKind.issue_reported: IssueReported,
    CardKind.cancel_requested: CancelRequested,
}


class CardCreate(BaseModel):
    kind: str
    payload: dict = Field(default_factory=dict)
    # Free text — encrypted at rest like any message.
    text: str | None = None
