import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Mirrors `schemas.cards.HandoverMethod`. Kept as a set here rather than
# imported to avoid a marketplace→cards dependency for one literal list.
HANDOVER_METHODS = {
    "in_person", "local_post", "courier", "parcel_locker", "poste_restante",
}


class TripCreate(BaseModel):
    origin: str
    destination: str
    depart_at: datetime
    capacity: float
    allowed_categories: list[str] | None = None
    # T3.35 — the carrier's baseline terms. Optional on purpose: a trip without
    # a stated price is a legitimate listing ("price on request"), and forcing a
    # number would make carriers invent one to get past the form.
    price_per_kg: float | None = Field(default=None, gt=0, le=10_000)
    min_deal_price: float | None = Field(default=None, ge=0, le=1_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    allowed_handover_methods: list[str] | None = None
    max_declared_value: float | None = Field(default=None, ge=0)
    # T_UX.11 — omitted means "use my standing rules"; an explicit empty string
    # means "this trip has none", and the two must stay distinguishable.
    carriage_rules: str | None = Field(default=None, max_length=4000)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("allowed_handover_methods")
    @classmethod
    def _known_methods(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        unknown = set(v) - HANDOVER_METHODS
        if unknown:
            raise ValueError(f"unknown handover methods: {sorted(unknown)}")
        return v


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
    capacity: float
    allowed_categories: list[str] | None
    # T3.35 — shown on the trip card so two trips on one corridor are
    # comparable before anyone opens a chat.
    price_per_kg: float | None = None
    min_deal_price: float | None = None
    currency: str = "USD"
    allowed_handover_methods: list[str] | None = None
    max_declared_value: float | None = None
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
    model_config = ConfigDict(from_attributes=True)


class DealEventOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    event_type: str
    payload: dict | None
    actor_id: uuid.UUID
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)
