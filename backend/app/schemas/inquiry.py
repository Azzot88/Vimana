import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InquiryOut(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    sender_id: uuid.UUID
    carrier_id: uuid.UUID
    deal_id: uuid.UUID | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InquiryMessageCreate(BaseModel):
    text: str


class InquiryMessageOut(BaseModel):
    id: uuid.UUID
    inquiry_id: uuid.UUID
    sender_id: uuid.UUID
    text: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
