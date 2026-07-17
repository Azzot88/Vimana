import uuid
from datetime import datetime
from typing import Any

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
    # T2.3 — for e2e messages the client needs raw ciphertext + own read_package
    # to decrypt. Server never fills `text` for e2e; `wrapped_shares` stays hidden
    # from the wire (only the dispute endpoint exposes arbiter's share).
    is_e2e: bool = False
    ciphertext_b64: str | None = None
    nonce_b64: str | None = None
    read_packages: dict[str, Any] | None = None
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
    # T2.3 — client-encrypted blob. When provided, `text` MUST be null; server
    # stores the blob opaque. Structure enforced by `core.threshold.E2EPayload`.
    e2e_payload: dict[str, Any] | None = None
