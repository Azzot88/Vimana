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
    # T3.11.23 — who the chat is with, by name. The list of chats is a list of
    # people, and a person named by a truncated uuid is a row nobody opens. Not
    # a role: today one of them sends and the other carries, tomorrow the other
    # way round, and the chat outlives both arrangements.
    counterparty_name: str | None = None
    # T3.11.23 — how many deals are nested here. The screen asks it to decide
    # whether to offer a choice at all: with one deal a picker is furniture, and
    # the owner asked for it «только если появляется вторая сделка».
    deal_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class InquiryMessageCreate(BaseModel):
    text: str
    # T3.11.23 — which trip this message is about, when it is about one.
    #
    # The trip stopped being the thread's identity and became the content of the
    # message that raises it. Without this the column exists and nothing ever
    # fills it — and the carrier's panel, which counts «сколько человек
    # спросили про этот рейс», has nothing left to count.
    #
    # Optional because most messages are not about a trip: they are the rest of
    # the conversation.
    about_trip_id: uuid.UUID | None = None


class InquiryMessageOut(BaseModel):
    id: uuid.UUID
    inquiry_id: uuid.UUID
    sender_id: uuid.UUID
    text: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
