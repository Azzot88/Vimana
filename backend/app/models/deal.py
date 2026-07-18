import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DealStatus(str, enum.Enum):
    draft = "draft"
    matched = "matched"
    accepted = "accepted"
    in_transit = "in_transit"
    delivered = "delivered"
    confirmed = "confirmed"
    closed = "closed"
    disputed = "disputed"


class DealEventType(str, enum.Enum):
    created = "created"
    matched = "matched"
    accepted = "accepted"
    handoff = "handoff"
    in_transit = "in_transit"
    received = "received"
    confirmed = "confirmed"
    closed = "closed"
    dispute_opened = "dispute_opened"
    arbiter_opened = "arbiter_opened"
    dispute_resolved = "dispute_resolved"


class DisputeStatus(str, enum.Enum):
    open = "open"
    claimed = "claimed"
    resolved = "resolved"


class AttachmentKind(str, enum.Enum):
    handoff_photo = "handoff_photo"
    receipt_photo = "receipt_photo"
    doc = "doc"
    payment_receipt = "payment_receipt"


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    carrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[DealStatus] = mapped_column(SAEnum(DealStatus), default=DealStatus.draft)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealEvent(Base):
    __tablename__ = "deal_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    event_type: Mapped[DealEventType] = mapped_column(SAEnum(DealEventType))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    nostr_sig: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nostr_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nostr_created_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nostr_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealVaultMessage(Base):
    __tablename__ = "deal_vault_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # T1.21: text is stored AES-256-GCM encrypted. `text` property below wraps
    # these two columns so callers keep using `msg.text` transparently.
    text_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    text_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    nostr_sig: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nostr_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nostr_created_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nostr_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # T2.3 — client-side threshold-encrypted blob. When is_e2e=true, server
    # cannot decrypt; `text` property returns None and callers ship the blob
    # straight to the client.
    is_e2e: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    wrapped_shares: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    read_packages: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="message", lazy="raise")

    @property
    def text(self) -> str | None:
        # T2.3: e2e messages are opaque to the server — never decrypt attempted.
        if self.is_e2e:
            return None
        if self.text_ciphertext is None or self.text_nonce is None:
            return None
        from app.core.crypto import decrypt
        return decrypt(bytes(self.text_nonce), bytes(self.text_ciphertext))

    @text.setter
    def text(self, value: str | None) -> None:
        if value is None:
            self.text_ciphertext = None
            self.text_nonce = None
            return
        from app.core.crypto import encrypt
        nonce, ct = encrypt(value)
        self.text_nonce = nonce
        self.text_ciphertext = ct


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        UniqueConstraint("deal_id", name="uq_disputes_deal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    opened_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    arbiter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[DisputeStatus] = mapped_column(SAEnum(DisputeStatus), default=DisputeStatus.open)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DealParticipantRole(str, enum.Enum):
    recipient = "recipient"


class DealParticipant(Base):
    """T3.3 — additional deal participants beyond sender/carrier/arbiter.

    Currently only `recipient` role: someone the sender invites to view (and
    write to) the chat. Recipient has their own custodial keypair (invisible
    to them) and is included in `read_packages` on every subsequent e2e
    message. Threshold scheme stays 2-of-3 {sender, carrier, arbiter}; recipient
    is orthogonal to it.

    Row is created with `user_id=NULL` at invite time; populated when the
    invitee accepts the link and their user gets bound. `invite_token` is
    the shareable secret in the URL.
    """

    __tablename__ = "deal_participants"
    __table_args__ = (
        UniqueConstraint("deal_id", "user_id", "role", name="uq_participant_deal_user_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    role: Mapped[DealParticipantRole] = mapped_column(
        SAEnum(DealParticipantRole), default=DealParticipantRole.recipient
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    invite_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OperatorAccessGrant(Base):
    """T3.2 — explicit consent from a deal participant to let the arbiter read
    DealVault for a given dispute.

    Opening a dispute auto-creates a grant from the opener (they de facto
    consent by escalating). The other party may add their own grant via
    `POST /disputes/{id}/grant-access` — useful when arbiter wants both sides
    on record (e.g., threshold recovery needs cooperation). Superuser bypasses
    grants; arbiter needs ≥1 non-revoked grant on the dispute to read.
    """

    __tablename__ = "operator_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "dispute_id", "granted_by", name="uq_grant_dispute_party"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disputes.id"))
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deal_vault_messages.id"))
    r2_key: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64))
    ipfs_cid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[AttachmentKind] = mapped_column(SAEnum(AttachmentKind))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    message: Mapped["DealVaultMessage"] = relationship("DealVaultMessage", back_populates="attachments", lazy="raise")
