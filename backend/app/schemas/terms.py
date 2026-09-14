from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.currencies import CURRENCIES
from app.schemas.cards import HandoverMethod, PaymentMethod

#: T3.12.04 — what used to be the «Груз» section and belongs to the cargo now.
#: `D-CARGO-MODEL`: the cargo is written once at the response and does not
#: change, so terms that carried their own weight or their own «хрупкое» would be
#: a second copy of the parcel that two people could edit. Named here so that a
#: client still sending them is refused by name, not silently ignored.
CARGO_FIELDS: frozenset[str] = frozenset(
    {
        "weight_kg",
        "dimensions_cm",
        "declared_value",
        "cargo_what",
        "cargo_packaging",
        "cargo_fragile",
        "cargo_open_on_handover",
        "cargo_url",
    }
)


class TermsIn(BaseModel):
    """A proposal from either side.

    `description` is the only free-text field and it goes to the encrypted
    column, not into the payload — the payload holds what the server has to be
    able to read (§6.9.3).

    T3.12.04 — no cargo. The weight and dimensions the price is normalised by
    are read from the deal's cargo (`api.terms._build_payload`).
    """

    price_total: float = Field(gt=0)
    # T3.11.07 — four characters, because `USDT` and `USDC` are four. A deal is
    # negotiated in the currency the trip was published in, so a limit narrower
    # than the trip's would refuse the ordinary continuation of that trip.
    currency: str = Field(default="USD", min_length=3, max_length=4)
    deadline: datetime | None = None
    payment_method: PaymentMethod = "cash_on_delivery"
    description: str | None = None
    # Set when countering: the proposal this one replaces.
    supersedes_id: uuid.UUID | None = None

    # ── T3.11.27 — the whole agreement, in sections ───────────────────────
    #
    # Owner's decision 2026-09-07: one card instead of four. The same facts used
    # to be spread across `terms.*`, `handover.conditions`, `pickup.proposed`
    # and `dropoff.proposed`, and «договориться о передаче» stood as a separate
    # step *after* both sides had agreed the deal — describing an agreement they
    # had already reached.
    #
    # The fields are flat with section prefixes rather than nested: the sections
    # exist to name what changed («изменены условия: Передача, Оплата»).
    # `SECTION_OF` in `core.cards` is what maps one to the other.
    #
    # All of them optional: a half-filled agreement is the normal state of the
    # first stage rather than an error.
    handover_method: HandoverMethod | None = None
    handover_place: str | None = Field(default=None, max_length=200)
    handover_at: datetime | None = None

    delivery_method: HandoverMethod | None = None
    delivery_place: str | None = Field(default=None, max_length=200)
    delivery_at: datetime | None = None

    #: T3.11.27 — who pays the carrier. It decides whose button closes the deal:
    #: «получил» and «рассчитался» are one press for the person who does both,
    #: and two presses when the recipient is somebody who owes nothing.
    payer: Literal["sender", "recipient"] = "sender"

    #: Sections the **carrier** has locked in this deal. A locked section is
    #: theirs to edit; everything else is open to both. Per deal rather than per
    #: trip (owner's decision 2026-09-07): a carrier is stricter with one sender
    #: and softer with another.
    locked: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _no_cargo(cls, data: Any) -> Any:
        if isinstance(data, dict):
            sent = sorted(CARGO_FIELDS & set(data))
            if sent:
                raise ValueError(
                    f"The cargo is not part of the terms: {', '.join(sent)}"
                )
        return data

    @field_validator("locked")
    @classmethod
    def _known_sections(cls, v: list[str]) -> list[str]:
        from app.core.cards import DEAL_SECTIONS

        unknown = set(v) - set(DEAL_SECTIONS)
        if unknown:
            raise ValueError(f"unknown sections: {sorted(unknown)}")
        return list(dict.fromkeys(v))

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, v: str) -> str:
        code = v.strip().upper()
        if code not in CURRENCIES:
            raise ValueError(f"unknown currency: {code}")
        return code


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
