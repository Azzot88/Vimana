"""T3.36–T3.39 — payload shapes, one per card kind.

Every model here holds only what the server must be able to read: enumerations,
amounts, dates. Free text and addresses travel in the message's encrypted `text`
column (§6.9.3), which is why none of these models has a `description` field
even where the card obviously has something to say.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.cards import CardKind

HandoverMethod = Literal[
    "in_person", "local_post", "courier", "parcel_locker", "poste_restante"
]


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
    currency: str = Field(default="USD", min_length=3, max_length=3)
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
