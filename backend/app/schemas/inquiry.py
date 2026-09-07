import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InquiryOut(BaseModel):
    """T3.11.23 — a chat, in the shape the client already reads.

    `id` is the chat's id now; `trip_id` is the trip the caller asked about, and
    it is **echoed from the request** rather than owned by the thread. That is
    the whole model change in one field: the trip used to be what the thread
    *was*, and is now what a message in it is about.

    `deal_id` is the open deal in this chat, if there is one. Several deals can
    live in one chat (owner's clarification 2026-09-07), so this is «the one to
    carry on in», not «the deal of this thread».
    """

    id: uuid.UUID
    trip_id: uuid.UUID | None = None
    sender_id: uuid.UUID
    carrier_id: uuid.UUID
    deal_id: uuid.UUID | None = None
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
