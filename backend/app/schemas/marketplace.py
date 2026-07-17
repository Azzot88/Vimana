import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TripCreate(BaseModel):
    origin: str
    destination: str
    depart_at: datetime
    capacity: float
    allowed_categories: list[str] | None = None


class TripOut(BaseModel):
    id: uuid.UUID
    carrier_id: uuid.UUID
    origin: str
    destination: str
    depart_at: datetime
    capacity: float
    allowed_categories: list[str] | None
    status: str
    created_at: datetime
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
