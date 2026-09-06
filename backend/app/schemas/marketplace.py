import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core.trip_legs import MAX_LEGS
from app.models.marketplace import EXCLUSIONS, TRIP_SERVICES


# Mirrors `schemas.cards.HandoverMethod`. Kept as a set here rather than
# imported to avoid a marketplace→cards dependency for one literal list.
HANDOVER_METHODS = {
    "in_person", "local_post", "courier", "parcel_locker", "poste_restante",
}


def _closed_list(
    value: list[str] | None, vocabulary: tuple[str, ...], what: str
) -> list[str] | None:
    """T3.11.07 — validate one of the trip's closed-vocabulary lists.

    Deduplicates rather than refuses a repeat: a repeated value is a client bug,
    not a carrier saying something twice, and stored it would draw the same chip
    twice on the card. `None` passes through untouched — "said nothing" is a
    real answer and a different one from an empty list.

    Called by: `TripCreate._known_exclusions`, `TripCreate._known_services`.
    """
    if value is None:
        return None
    unknown = set(value) - set(vocabulary)
    if unknown:
        raise ValueError(f"unknown {what}: {sorted(unknown)}")
    return list(dict.fromkeys(value))


class TripLegIn(BaseModel):
    """T3.11.15 — one flight of the chain. `leg_order` is assigned on write, not
    submitted: see `core.trip_legs.normalise_legs`."""

    origin: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    depart_at: datetime
    # Declared, never inferred. "Flying in person" is the most valuable claim on
    # this market and the one nothing checks today.
    flown_by: Literal["self", "proxy"] = "self"


class TripLegOut(BaseModel):
    # The column is `leg_order` (`order` is reserved in SQL) but the wire word is
    # `order`: the client has no reason to inherit a database workaround.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    order: int = Field(validation_alias=AliasChoices("leg_order", "order"))
    origin: str
    destination: str
    depart_at: datetime
    flown_by: str


class HandoverSide(BaseModel):
    """T3.11.15 — how the carrier takes cargo at one end of the route.

    `points` is free text on purpose: the market names districts, suburbs and
    satellite cities ("Tustin, Irvine or LAX", "Fili, Moscow"), and a picker
    over airports cannot say any of that. Bounded rather than validated — a
    taxonomy of neighbourhoods is not something this task can be right about.
    """

    methods: list[str] = Field(default_factory=list, max_length=len(HANDOVER_METHODS))
    points: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("methods")
    @classmethod
    def _known_methods(cls, v: list[str]) -> list[str]:
        unknown = set(v) - HANDOVER_METHODS
        if unknown:
            raise ValueError(f"unknown handover methods: {sorted(unknown)}")
        return v

    @field_validator("points")
    @classmethod
    def _trim_points(cls, v: list[str]) -> list[str]:
        cleaned = [p.strip() for p in v if p and p.strip()]
        for point in cleaned:
            if len(point) > 120:
                raise ValueError("a handover point is at most 120 characters")
        return cleaned


class TripCreate(BaseModel):
    # T3.11.15 — the route arrives as a chain and only as a chain. The flat
    # `origin`/`destination`/`depart_at` trio is gone from the wire: keeping it
    # alongside `legs` would mean two ways to say the same thing and a rule
    # about which one wins. The columns of those names survive on the model as
    # the denormalised head of the chain — see `core.trip_legs.head_and_tail`.
    legs: list[TripLegIn] = Field(min_length=1, max_length=MAX_LEGS)
    # T3.11.07 — optional since the express path. The route is the only thing a
    # carrier must state to be findable; everything else is a detail they can
    # add later, and 31 % of this market publishes inside two days of the
    # flight. Weight in kilograms is stated in 2.4 % of real posts.
    capacity: float | None = Field(default=None, gt=0, le=100)
    allowed_categories: list[str] | None = None
    # T3.35 — the carrier's baseline terms. Optional on purpose: a trip without
    # a stated price is a legitimate listing ("price on request"), and forcing a
    # number would make carriers invent one to get past the form.
    price_per_kg: float | None = Field(default=None, gt=0, le=10_000)
    min_deal_price: float | None = Field(default=None, ge=0, le=1_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    max_declared_value: float | None = Field(default=None, ge=0)
    # T3.11.07 — a closed list, so a sender can filter on it. `None` means the
    # carrier said nothing, which is what 94 % of this market does; an empty
    # list would claim they considered the question and had no exclusions.
    excluded: list[str] | None = Field(default=None, max_length=len(EXCLUSIONS))
    # T3.11.07 — what the carrier does around the flight, and how they expect to
    # be paid. Both nullable: the settlement model is stated by 61.7 % of this
    # market and a price by 0.1 %, so the model is the field that matters — but
    # silence still has to stay distinguishable from the commonest answer.
    services: list[str] | None = Field(default=None, max_length=len(TRIP_SERVICES))
    payment_model: Literal["on_platform", "off_platform"] | None = None
    # Free text turned into chips by the form, not a closed list: what people
    # transfer through is local and changes faster than a vocabulary we could
    # ship, and a carrier naming one we had not heard of would be told they are
    # wrong.
    payment_systems: list[str] | None = Field(default=None, max_length=8)
    # T_UX.15 — omitted means "use my standing rules"; an explicit empty string
    # means "this trip has none", and the two must stay distinguishable.
    carriage_rules: str | None = Field(default=None, max_length=4000)
    space_kind: Literal[
        "cabin", "checked_partial", "checked_full", "unspecified"
    ] = "unspecified"
    size_hint: Literal["small", "medium", "large"] | None = None
    # T3.11.15 — asymmetric by design. These replace the single
    # `allowed_handover_methods` list: once both ends are stated separately, one
    # combined list is a second way to say the same thing.
    handover_origin: HandoverSide | None = None
    handover_destination: HandoverSide | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("excluded")
    @classmethod
    def _known_exclusions(cls, v: list[str] | None) -> list[str] | None:
        return _closed_list(v, EXCLUSIONS, "exclusions")

    @field_validator("services")
    @classmethod
    def _known_services(cls, v: list[str] | None) -> list[str] | None:
        return _closed_list(v, TRIP_SERVICES, "services")

    @field_validator("payment_systems")
    @classmethod
    def _clean_systems(cls, v: list[str] | None) -> list[str] | None:
        """Trimmed, deduplicated, bounded — but not checked against a list.

        The form turns typed text into chips, so what arrives is whatever the
        carrier called it. Blanks are dropped rather than rejected: a trailing
        comma is a typo, not an answer, and refusing the whole trip over one is
        the wrong trade.
        """
        if v is None:
            return None
        cleaned = [s.strip() for s in v if s and s.strip()]
        for system in cleaned:
            if len(system) > 40:
                raise ValueError("a payment system name is at most 40 characters")
        return list(dict.fromkeys(cleaned)) or None


class TripOut(BaseModel):
    id: uuid.UUID
    carrier_id: uuid.UUID
    carrier_name: str | None = None
    # T3.1/T3.2 — UBA is a first-class trust signal on trip cards.
    carrier_uba: int | None = None
    carrier_uba_level: str | None = None
    # T3.17 — a retired identity, visible before anyone offers it a deal. The
    # account can still be signed into but can no longer act, and finding that
    # out after choosing a carrier is finding it out too late.
    carrier_key_lost: bool = False
    origin: str
    destination: str
    depart_at: datetime
    capacity: float | None = None
    allowed_categories: list[str] | None
    # T3.35 — shown on the trip card so two trips on one corridor are
    # comparable before anyone opens a chat.
    price_per_kg: float | None = None
    min_deal_price: float | None = None
    currency: str = "USD"
    # T3.11.07 — the customs allowance the carrier has left, not a ceiling.
    max_declared_value: float | None = None
    space_kind: str = "unspecified"
    size_hint: str | None = None
    handover_origin: dict | None = None
    handover_destination: dict | None = None
    legs: list[TripLegOut] = Field(default_factory=list)
    excluded: list[str] | None = None
    services: list[str] | None = None
    payment_model: str | None = None
    payment_systems: list[str] | None = None
    carriage_rules: str | None = None
    status: str
    created_at: datetime
    # T3.5 — Nostr publish state (surfaced to clients for the "📡 Also on Nostr" chip).
    nostr_event_id: str | None = None
    nostr_published_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    recipient_contact: str
    origin: str
    destination: str
    category: str
    declared_value: float
    currency: str = "USD"
    description: str | None = None
    deadline: datetime | None = None


class DealOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    trip_id: uuid.UUID
    sender_id: uuid.UUID
    carrier_id: uuid.UUID
    recipient_id: uuid.UUID | None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DealDetailOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    trip_id: uuid.UUID
    sender_id: uuid.UUID
    carrier_id: uuid.UUID
    recipient_id: uuid.UUID | None
    status: str
    created_at: datetime
    origin: str
    destination: str
    depart_at: datetime
    sender_name: str
    carrier_name: str
    # T2.3 — needed by client to encrypt vault messages under both parties' npubs.
    sender_npub: str | None = None
    carrier_npub: str | None = None
    cargo_description: str
    cargo_category: str
    declared_value: float
    currency: str
    # T_UX.15 — the rules the sender agreed to when they chose this trip. Read
    # from the trip's own copy, not the carrier's current template: a rule
    # edited after the match is not the rule this deal was struck under.
    carriage_rules: str | None = None
    model_config = ConfigDict(from_attributes=True)


class DealEventOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    event_type: str
    payload: dict | None
    actor_id: uuid.UUID
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)
