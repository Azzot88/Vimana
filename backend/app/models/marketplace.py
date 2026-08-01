import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TripStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    matched = "matched"
    completed = "completed"
    cancelled = "cancelled"


DEFAULT_CATEGORIES = ("document", "medicine", "electronics", "gift", "animal", "other")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrderStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    matched = "matched"
    closed = "closed"
    cancelled = "cancelled"


class Trip(Base):
    __tablename__ = "trips"
    # Marketplace listing filters on status and pages by (created_at, id);
    # the second index serves a carrier's own trips (T_PERF.1, 0034).
    __table_args__ = (
        Index("ix_trips_status_created", "status", "created_at", "id"),
        Index("ix_trips_carrier_id", "carrier_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    carrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    origin: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    depart_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[float] = mapped_column(Float)
    allowed_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[TripStatus] = mapped_column(SAEnum(TripStatus), default=TripStatus.draft)
    # T3.5 — Nostr publication tracking. Unique event_id enforces idempotency
    # for the replaceable kind-30402 event (updates rewrite in-place).
    nostr_event_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    nostr_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # T3.12 — which key signed the published event. NIP-09 requires a deletion
    # to be signed by the same key that published, so this cannot be inferred
    # from the carrier's *current* key once they move to their own.
    nostr_published_by_pubkey: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_contact: Mapped[str] = mapped_column(String(255))
    origin: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50))
    declared_value: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), default=OrderStatus.draft)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TripInquiry(Base):
    """T1.22: pre-deal chat thread between a sender and the trip's carrier.
    Unique per (trip_id, sender_id) — reuse the same thread if sender re-opens."""
    __tablename__ = "trip_inquiries"
    __table_args__ = (
        UniqueConstraint("trip_id", "sender_id", name="uq_trip_inquiries_trip_sender"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    carrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InquiryMessage(Base):
    """T1.22: encrypted messages inside a TripInquiry thread. Same at-rest
    scheme as DealVaultMessage (T1.21) — `text` is a property that wraps the
    ciphertext/nonce columns."""
    __tablename__ = "inquiry_messages"
    # Same read shape as the vault chat: filter by thread, order by time
    # (T_PERF.1, 0034).
    __table_args__ = (
        Index("ix_inquiry_messages_inquiry_created", "inquiry_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    inquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trip_inquiries.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    text_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    text_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def text(self) -> str | None:
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
