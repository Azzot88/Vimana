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


# T3.11.07 — ordered by how often the market names each thing, measured over
# 15 128 messages (TASKS.md, «Разбор переписок рынка»): documents 86.2 %,
# parcels ≈71, clothing and personal effects 34, medicine 32.8, electronics 15,
# animals 9.1, gifts 8.8. `parcel` and `clothing` were missing entirely — the
# two commonest words on this market after "documents" had no key to be filed
# under, so a carrier saying "возьму посылки" could not say it here at all.
#
# Order matters: it seeds `Category.sort_order`, and since the owner named the
# order outright (2026-09-06) that seed is the whole rule — `usage_count` no
# longer outranks it. This tuple is the picker, in the order it is drawn.
DEFAULT_CATEGORIES = (
    "document",
    "clothing",
    "electronics",
    "medicine",
    "animal",
    "art",
    "other",
)

# T3.11.07 — retired from the picker (owner's decision 2026-09-06), not deleted.
# `parcel` was added the same day off the market analysis (≈71 % of posts say
# «возьму посылки») and taken back out because a parcel is the container, not the
# cargo: everything on this market is a parcel, so as a category it says nothing
# and would be ticked by everyone. `gift` has existed since 0003 and real trips
# may carry it.
#
# Rows stay so those trips keep a label; `is_active` is what removes them from
# the picker. Deleting them would leave `allowed_categories` pointing at keys
# with nothing behind them.
RETIRED_CATEGORIES = ("parcel", "gift")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # T3.11.07 — where this sits in the picker. Seeded from `DEFAULT_CATEGORIES`
    # and **not** overridden by traffic (owner's decision 2026-09-06): a stated
    # order is not a tie for `usage_count` to break, and a picker that quietly
    # rearranges itself as deals close is one where muscle memory lands on the
    # wrong chip. Carrier-added categories default to the end.
    sort_order: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    # T3.11.07 — offered in the picker. Separate from `is_default`, which means
    # "shipped with the product": a category can be ours and retired at the same
    # time, and overloading one flag with both meanings would lose the
    # difference the first time somebody asked why `gift` is still in the list.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
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
            "buyout_paid_by IS NULL OR "
            "buyout_paid_by IN ('sender_prepaid','carrier_credit')",
            name="ck_trips_buyout_paid_by",
        ),
        CheckConstraint(
            "buyout_limit IS NULL OR buyout_limit > 0",
            name="ck_trips_buyout_limit",
        ),
        CheckConstraint(
            "payment_model IS NULL OR "
            "payment_model IN ('cash_on_delivery','emoney_on_delivery',"
            "'platform_wallet')",
            name="ck_trips_payment_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    carrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    origin: Mapped[str] = mapped_column(String(100))
    destination: Mapped[str] = mapped_column(String(100))
    depart_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # T3.11.16 — when the trip stops being a listing: the departure of its
    # **last** leg, denormalised on write like `origin`/`destination`/`depart_at`
    # are denormalised from the first. The board hides what has already flown
    # without anybody pressing anything — at a median horizon of five days, a
    # board without this fills with trips that no longer exist inside a week.
    #
    # Nullable only for rows written before the column existed; the listing
    # treats null as «no answer» and keeps showing them rather than hiding
    # history it cannot date.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
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
    # T3.11.07 — four characters, not three: `USDT` and `USDC` are four, and an
    # account can now price in them. A carrier whose primary currency is a
    # stablecoin would otherwise have every publication truncated or refused.
    currency: Mapped[str] = mapped_column(String(4), default="USD", server_default="USD")
    # T3.11.07 — the customs allowance the carrier has **left** on this flight,
    # not a ceiling they are prepared to cover.
    #
    # It carried a companion `declared_value_status ∈ {open, exhausted}` for a
    # few hours; the owner removed it (2026-09-06) and the reason holds: once
    # the number means "free", zero already says "spent", and a separate state
    # is a second place for the same fact to be wrong. The label the carrier
    # reads says «свободный таможенный лимит» for exactly that reason.
    max_declared_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # T3.11.07 — the allowance has a currency of its own (owner's decision
    # 2026-09-06), and it is **not** `Trip.currency`. A customs allowance is
    # denominated by the country the parcel lands in — $2 000 into the US — while
    # the price is whatever the carrier quotes in, and those are routinely two
    # different currencies. One shared field would mean picking the allowance's
    # currency silently re-prices the trip.
    #
    # `NULL` means "the trip's currency", which is the common case and keeps the
    # form from having to answer a question nobody asked.
    max_declared_value_currency: Mapped[str | None] = mapped_column(
        String(4), nullable=True
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
    # T3.11.07 — what this carrier will not take, from a closed list. Only
    # 5.9 % of real posts state exclusions at all, and when they do the wording
    # is nearly always one of five things: cigarettes, alcohol, tobacco, food,
    # luxury goods. A free-text field for that produces five spellings of
    # "сигареты" and nothing a filter can read; the free text below stays for
    # everything the list does not cover.
    excluded: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # T3.11.07 — what the carrier does around the flight. See `TRIP_SERVICES`.
    services: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # T3.11.07 — the settlement model, which the market states far more often
    # than it states a price. NULL is "did not say", and that is not the same
    # as `on_delivery`, however common that answer is.
    payment_model: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # T3.11.07 — which transfer systems, when the model is a transfer after
    # delivery. Free text turned into chips rather than a closed list: what
    # people transfer through is local and changes faster than any vocabulary
    # we could ship, and a carrier naming one we had not heard of would
    # otherwise be told they are wrong.
    payment_systems: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # T3.11.18 — the two answers `purchase_on_request` cannot be offered
    # without. Nullable because most trips do not offer the service at all;
    # required **together with it** by `TripCreate`, which is where the pairing
    # is enforced rather than by a constraint that cannot see the services list.
    buyout_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    buyout_paid_by: Mapped[str | None] = mapped_column(String(24), nullable=True)
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
# T3.11.07 — the exclusions carriers actually write, and nothing else. Taken
# from the market analysis (TASKS.md, «Разбор переписок рынка»): "не беру
# сигареты", "алкоголь не беру", "люкс НЕ беру", "не беру еду". Cigarettes and
# tobacco are one entry because they are one refusal written two ways.
#
# Cash is deliberately absent (owner's decision 2026-09-06). The platform takes
# no position on it in either direction — neither a ban nor an advertised
# option — and a carrier with something to say about it says it in the trip's
# free-text description. It was briefly present in 0061 and removed in 0062.
EXCLUSIONS = ("tobacco", "alcohol", "food", "luxury")

# T3.11.07 — what the carrier does around the flight, not on it. Every one of
# these is something the market already sells and the platform could not see:
# onward shipping inside the destination country appears in 44.9 % of posts,
# marketplace pickup in 19 %, buying goods to order in 18 %, door delivery in
# 8 %, photo reports in 1.7 %. Declared on the trip so the search can find them;
# what they mean for a deal's lifecycle is T3.11.17.
TRIP_SERVICES = (
    "domestic_shipping",
    "marketplace_pickup",
    "purchase_on_request",
    "door_delivery",
    "photo_report",
)

# T3.11.18 — buying goods to order, and the two answers that make it safe to
# offer at all (owner's decision 2026-09-08).
#
# **The fraud is documented verbatim in the market dump:** «Сначала просит
# зубную щётку выкупить, а потом ирригатор! По итогу оплачиваешь щётку,
# доставку, а на следующий день…». What is at risk here is the **carrier's**
# money — $2 000 of bought goods, not the $50 carriage fee — and 42.6 %
# «без предоплаты» is not generosity, it is a negotiating position taken by
# people who have been asked for money up front.
#
# So `purchase_on_request` in `TRIP_SERVICES` cannot stand alone. A carrier who
# ticks it must also say **how much** they are willing to lay out and **who pays
# for the goods**, because a form that offers the service without those two
# fields reproduces the scheme above with a logo on it.
#
# Until Фаза 5 there is no money on the platform, so this is a **declared limit
# and a record**, not a guarantee. `§9.1`: no screen calls it protection.
BUYOUT_PAID_BY = ("sender_prepaid", "carrier_credit")

# T3.11.07 — how the carrier expects to be paid. **Three, and answering is
# obligatory** (owner's decision 2026-09-08, replacing the two optional models
# of 2026-09-06).
#
# The three separate *when* and *where the money lives*, which is the pair that
# actually differs for the two people:
#   `cash_on_delivery`   — наличными при получении
#   `emoney_on_delivery` — электронными деньгами при получении
#   `platform_wallet`    — с кошелька на платформе
#
# The previous revision collapsed the first two into `off_platform` on the
# grounds that «cash or transfer?» is the same question as «which system?».
# That was right about the words and wrong about the people: cash is settled
# hand to hand at the door and e-money is settled by two phones, and a sender
# who cannot carry notes needs to know which one before they agree, not after.
# `payment_systems` keeps saying *which* service, and now only makes sense
# beside `emoney_on_delivery` — cash has no system to name.
#
# **Obligatory, and still changeable.** The trip states the carrier's model; the
# deal's agreement carries a `payment` section both sides confirm, so the two of
# them may settle differently by agreeing to. Obligatory here means the carrier
# cannot publish without answering — 61.7 % of this market states the model
# anyway, and the sender who has to ask is the one who does not book.
#
# Existing rows are mapped, never guessed at: `on_platform → platform_wallet`,
# and `off_platform` splits by whether the carrier named any system — a named
# system *is* the answer «электронными», an empty list is cash. Rows that said
# nothing stay NULL: the column is nullable on purpose, because a trip published
# before the question existed did not answer it, and writing an answer in would
# be the platform speaking for its carriers.
PAYMENT_MODELS = ("cash_on_delivery", "emoney_on_delivery", "platform_wallet")

#: The model that needs `payment_systems` beside it, and the only one.
EMONEY_MODEL = "emoney_on_delivery"

# T3.11.07 — which system, when the money moves as e-money on delivery.
# The catalogue lives in `core/payment_systems.py`; free text stays allowed,
# because what people settle through is local and outlives any list we ship.



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
    # T3.11.07 — when this flight lands (owner's decision 2026-09-06). Nullable,
    # and the form asks it only for the **end of the route**: that is the time a
    # sender needs — when the parcel can be collected — and a carrier who knows
    # the landing hour of each intermediate hop is rare. Null is a real answer,
    # not a gap, and every trip published before this revision carries one.
    arrive_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    # T3.11.07 — four characters, matching `Trip.currency`: an order is priced
    # in what the trip it answers was published in.
    currency: Mapped[str] = mapped_column(String(4), default="USD")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), default=OrderStatus.draft)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Chat(Base):
    """T3.11.23 — one chat per person, and only one, forever.

    Owner's model, 2026-09-07: «Чаты привязаны к пользователям и существуют в
    единственном числе на человека. Сделок может быть много… Сделка это чат,
    вложенный в чат.» The nested chat already existed — `Deal` plus
    `DealVaultMessage` is exactly that. What did not was the outer one.

    It replaces `TripInquiry`, which was keyed `(trip_id, sender_id)`: writing to
    one carrier about three trips produced three threads with the same person,
    and none of them was «our conversation».

    **The pair is stored ordered**, low id first, so `(A, B)` and `(B, A)` are
    one row rather than a rule every caller has to remember. The unique index is
    what makes «existing in a single copy per person» a fact of the database
    instead of a habit of the code.

    Roles are deliberately absent. A pair is a pair: today one of them sends and
    the other carries, tomorrow it is the other way round, and a chat that had
    baked the roles in would need a second row for the same two people.
    """

    __tablename__ = "chats"
    __table_args__ = (
        UniqueConstraint("user_low_id", "user_high_id", name="uq_chats_pair"),
        CheckConstraint("user_low_id < user_high_id", name="ck_chats_pair_ordered"),
        Index("ix_chats_low", "user_low_id"),
        Index("ix_chats_high", "user_high_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_low_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    user_high_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatMessage(Base):
    """T3.11.23 — a message in the outer chat. Encrypted at rest like every
    other message on this platform (T1.21): `text` is a property over the
    ciphertext/nonce pair.

    Was `InquiryMessage`, keyed to a per-trip thread.

    `about_trip_id` is how «рейс становится содержимым, а не личностью треда»
    survives contact with the carrier's panel. That panel counts how many people
    asked about a given trip, and with one thread per person there is no
    per-trip thread left to count — so the trip moves onto the message that
    mentions it. The count becomes «chats with a message about this trip», which
    is the same number and a truer sentence.
    """

    __tablename__ = "chat_messages"
    # Same read shape as the vault chat: filter by thread, order by time
    # (T_PERF.1, 0034).
    __table_args__ = (
        Index("ix_chat_messages_chat_created", "chat_id", "created_at", "id"),
        Index("ix_chat_messages_about_trip", "about_trip_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    about_trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trips.id"), nullable=True
    )
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
