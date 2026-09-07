from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.currencies import CURRENCIES

PaymentMethod = Literal["cash", "platform", "escrow"]


class TermsIn(BaseModel):
    """A proposal from either side.

    `description` is the only free-text field and it goes to the encrypted
    column, not into the payload — the payload holds what the server has to be
    able to read (§6.9.3).
    """

    weight_kg: float = Field(gt=0, le=100)
    price_total: float = Field(gt=0)
    declared_value: float = Field(ge=0)
    # T3.11.07 — four characters, because `USDT` and `USDC` are four. A deal is
    # negotiated in the currency the trip was published in, so a limit narrower
    # than the trip's would refuse the ordinary continuation of that trip.
    currency: str = Field(default="USD", min_length=3, max_length=4)
    dimensions_cm: list[float] | None = None
    deadline: datetime | None = None
    payment_method: PaymentMethod = "cash"
    description: str | None = None
    # Set when countering: the proposal this one replaces.
    supersedes_id: uuid.UUID | None = None

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, v: str) -> str:
        code = v.strip().upper()
        if code not in CURRENCIES:
            raise ValueError(f"unknown currency: {code}")
        return code

    @field_validator("dimensions_cm")
    @classmethod
    def _three_positive(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return None
        if len(v) != 3 or any(x <= 0 for x in v):
            raise ValueError("dimensions_cm must be three positive numbers")
        return v


class TermsOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    card_kind: str
    card_state: str
    requires_ack_by: str | None
    supersedes_id: uuid.UUID | None
    payload: dict[str, Any]
    description: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_message(cls, msg) -> "TermsOut":
        return cls(
            id=msg.id,
            deal_id=msg.deal_id,
            card_kind=msg.card_kind,
            card_state=msg.card_state.value if msg.card_state else "pending",
            requires_ack_by=(
                msg.requires_ack_by.value if msg.requires_ack_by else None
            ),
            supersedes_id=msg.supersedes_id,
            payload=msg.card_payload or {},
            description=msg.text,
            created_at=msg.created_at,
        )
