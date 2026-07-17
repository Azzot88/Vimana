import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    r2_key: str
    file_hash: str
    ipfs_cid: str | None
    kind: str
    url: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    sender_id: uuid.UUID | None
    text: str | None
    is_system: bool
    nostr_sig: str | None = None
    nostr_event_id: str | None = None
    nostr_created_at: int | None = None
    nostr_pubkey: str | None = None
    attachments: list[AttachmentOut]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    text: str | None = None
    is_system: bool = False
    # T2.2 pt.2 — self-custody clients pre-sign via NIP-07. Both fields must
    # come together; server rejects one-without-the-other.
    nostr_sig: str | None = None
    nostr_created_at: int | None = None
