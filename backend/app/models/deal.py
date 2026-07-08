import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, JSON, String, Text, UniqueConstraint, func
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
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealVaultMessage(Base):
    __tablename__ = "deal_vault_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    nostr_sig: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="message", lazy="raise")


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
