import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TripStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    matched = "matched"
    completed = "completed"
    cancelled = "cancelled"


DEFAULT_CATEGORIES = ("document", "medicine", "electronics", "gift", "animal", "art", "other")


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
        # T3.11.15 — the vocabularies are checked in the database, not only in
        # the request schema. A rule that lives in the API is bypassed by the
        # CLI, a fixture and a migration, and the row that slips through is
        # indistinguishable from a correct one afterwards (same reasoning as
        # T3.11.01: validation belongs to the model).
        CheckConstraint(
            "space_kind IN ('cabin','checked_partial','checked_full','unspecified')",
            name="ck_trips_space_kind",
        ),
        CheckConstraint(
            "size_hint IS NULL OR size_hint IN ('small','medium','large')",
            name="ck_trips_size_hint",
        ),
        CheckConstraint(
            "declared_value_status IN ('open','exhausted')",
            name="ck_trips_declared_value_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    carrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    origin: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    depart_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # T3.11.07 — nullable since the express path. The median carrier publishes
    # five days before departure and 31 % inside two days; a required weight is
    # a third field standing between "I am flying tomorrow at 23:40" and a
    # listing, and it is the field 97.6 % of real posts never answer in
    # kilograms at all. NULL means "not stated", which `size_hint` often
    # answers better anyway.
    capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    allowed_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # T3.35 — the carrier's baseline terms. Before this the model carried no
    # price at all, so every deal had to invent one in chat and nothing was
    # comparable between trips.
    price_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_deal_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    # Informational until the standing bond exists (T5.1a): declares what the
    # carrier is prepared to cover, so a sender can filter before matching.
    max_declared_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # T3.11.15 — the customs allowance is a *balance the carrier spends*, not a
    # threshold. The market says so in as many words: "лимит на люкс уже занят"
    # sits in posts that still take documents on the same flight. So the ceiling
    # (`max_declared_value`) and whether it is used up are two facts, and one
    # number cannot carry both.
    declared_value_status: Mapped[str] = mapped_column(
        String(10), default="open", server_default="open", nullable=False
    )
    bond_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # T3.11.15 — physical room, the other capacity. `capacity` stays the number
    # of kilograms; these two say what kind of room it is and how big a thing
    # fits. Weight in kg appears in 2.4 % of real posts and "small / not big"
    # in 9.9 %, so a kilogram slider alone asks a question most carriers do not
    # answer.
    space_kind: Mapped[str] = mapped_column(
        String(16), default="unspecified", server_default="unspecified", nullable=False
    )
    size_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # T3.11.15 — accepting and handing over are two different arrangements with
    # two different geographies, routinely asymmetric: "in Italy I take it at my
    # address or meet in Milan; in Russia I accept a courier at home". These
    # two replace the single `allowed_handover_methods` list, which could not
    # say that and, once both ends existed, was a second way to state the same
    # thing. Shape: {"methods": [...], "points": ["Tustin", "Irvine"]}.
    handover_origin: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    handover_destination: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # T_UX.15 — a copy of the carrier's standing rules, taken at publish time.
    # A copy on purpose: rules edited later must not rewrite what a sender read
    # when they chose this trip.
    carriage_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    legs: Mapped[list["TripLeg"]] = relationship(
        back_populates="trip",
        order_by="TripLeg.leg_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# T3.11.15 — vocabularies, declared next to the model that enforces them so the
# request schema and the check constraint cannot drift apart.
SPACE_KINDS = ("cabin", "checked_partial", "checked_full", "unspecified")
SIZE_HINTS = ("small", "medium", "large")
DECLARED_VALUE_STATUSES = ("open", "exhausted")
FLOWN_BY = ("self", "proxy")


class TripLeg(Base):
    """One flight of a trip.

    T3.11.15. A trip is a chain, not a pair of cities: 36.6 % of real carrier
    posts carry two or more dates and 15.0 % three or more cities
    (`Москва — Майами — Лос-Анджелес — Портленд`, `Майами — Москва (выход в
    Стамбуле)`). A "return flight" toggle expresses the first case and not the
    second, so the model takes an ordered list from the start — this is the one
    decision here that is expensive to change afterwards.

    `Trip.origin` / `destination` / `depart_at` stay as the denormalised first
    and last node. Search, the board, the Nostr event and the T3.11.06 countdown
    all stand on them; moving them into the chain would mean touching every one
    of those at once for no gain.
    """

    __tablename__ = "trip_legs"
    __table_args__ = (
        UniqueConstraint("trip_id", "leg_order", name="uq_trip_legs_order"),
        CheckConstraint("leg_order >= 0", name="ck_trip_legs_order_nonneg"),
        CheckConstraint("origin <> destination", name="ck_trip_legs_distinct"),
        CheckConstraint("flown_by IN ('self','proxy')", name="ck_trip_legs_flown_by"),
        Index("ix_trip_legs_trip_order", "trip_id", "leg_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    # Named `leg_order` rather than `order`: the bare word is reserved in SQL and
    # survives only as long as every reader remembers to quote it.
    leg_order: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    depart_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # T3.11.15 — who is actually on the plane. 16.9 % of posts say "flying in
    # person, no intermediaries" and some of those same posts say "(a friend is
    # flying)". The claim is the most valuable signal on this market and today
    # it is backed by nothing, so it becomes a field: peer verification
    # (USERJOURNEY §3a) has to apply to whoever crosses the border, not to
    # whoever runs the account. `proxy` is declared, not forbidden — most of the
    # volume is intermediated and a ban would simply keep it away.
    flown_by: Mapped[str] = mapped_column(
        String(8), default="self", server_default="self", nullable=False
    )

    trip: Mapped["Trip"] = relationship(back_populates="legs")


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
