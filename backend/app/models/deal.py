import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DealStatus(str, enum.Enum):
    draft = "draft"
    matched = "matched"
    accepted = "accepted"
    in_transit = "in_transit"
    # T3.11.17 — handed to a postal service inside the destination country.
    # 44.9 % of carriers on this market post the parcel onward after landing, so
    # for half the deals there is a leg between «in the carrier's hands» and
    # «in the recipient's», and the model knew nothing between `handoff` and
    # `received`. That gap is what made an arbiter's question — on which leg was
    # it lost — unanswerable from the record.
    posted = "posted"
    delivered = "delivered"
    confirmed = "confirmed"
    closed = "closed"
    # T3.11.27 — called off before the parcel moved, by both sides or by a
    # timeout nobody answered. Its own state and not `closed`: a deal that was
    # cancelled is not a deal that was completed, and the record has to be able
    # to tell somebody's cancellation rate from their delivery rate.
    cancelled = "cancelled"
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
    # T3.7 — vault-content chain events: the chain covers messages/files/identity,
    # not just status transitions.
    message_added = "message_added"
    file_added = "file_added"
    sealed = "sealed"
    identity_ref = "identity_ref"
    # T3.11.25 — a file that already existed, attached to *this* deal today.
    # Deliberately not `file_added`: the bytes were provided in March under a
    # different parcel, and a record saying they were provided here would be
    # false in the one place the product exists to keep true. Same hash, own
    # event, its own date.
    file_reattached = "file_reattached"
    # T3.11.27 — the deal was called off. Distinct from `closed` for the same
    # reason the status is: a cancellation is not a completion.
    cancelled = "cancelled"
    # T3.11.17 — the parcel was handed to a postal service inside the
    # destination country. Its own event because it is its own leg: the carrier
    # is done, the parcel is not there yet, and an arbiter asked «where was it
    # lost» needs to see which of the two answers the record supports.
    posted = "posted"


class CardState(str, enum.Enum):
    """T3.34 — lifecycle of a typed card.

    A card is never edited. `superseded` is how a correction looks: the newer
    card points back through `supersedes_id` and the older one stops counting.
    """

    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    superseded = "superseded"


class CardAckRole(str, enum.Enum):
    """Who owes the answer. Resolved against `Deal.sender_id` / `carrier_id` /
    `recipient_id`; `operator` is the arbiter surface."""

    sender = "sender"
    carrier = "carrier"
    recipient = "recipient"
    operator = "operator"


class DisputeStatus(str, enum.Enum):
    open = "open"
    claimed = "claimed"
    resolved = "resolved"


class AttachmentKind(str, enum.Enum):
    handoff_photo = "handoff_photo"
    receipt_photo = "receipt_photo"
    doc = "doc"
    payment_receipt = "payment_receipt"
    # T3.9 — full copy of a verified identity document, created ONLY by the
    # verification flow (not uploadable via the generic attachment endpoint:
    # it has no entry in ALLOWED_MIME_BY_KIND, so a manual attempt gets 415).
    identity_doc = "identity_doc"
    # T3.11.17 — the parcel photographed **before it was sealed**, which is the
    # only moment its contents are visible and already packed. `USERJOURNEY`
    # Этап 4a: the carrier's responsibility ends at the tracking code, and this
    # is the evidence that what went into the box is what was agreed.
    #
    # Not `handoff_photo` reused: an arbiter reads these labels, and «фото
    # передачи» on a picture of an open parcel would misdescribe the one piece
    # of evidence the postal leg has.
    pre_seal_photo = "pre_seal_photo"
    # T3.11.27 — «вот что я отправляю», shown at the terms stage, before the
    # carrier agrees to anything. Owner's decision 2026-09-07: a photo **or** a
    # link (`terms.cargo_url`) — whichever the sender has. The same slot is what
    # a buy-and-carry deal will use for the item being bought (`T3.11.17` part 2).
    #
    # Its own kind rather than `doc`: an arbiter reads these labels, and this one
    # is evidence of what the parcel was *before* anybody packed or carried it —
    # the only picture in the record taken while the deal could still be refused.
    cargo_photo = "cargo_photo"


class Deal(Base):
    __tablename__ = "deals"
    # `GET /api/deals` filters on either side of the deal (T_PERF.1, 0034).
    __table_args__ = (
        Index("ix_deals_sender_id", "sender_id"),
        Index("ix_deals_carrier_id", "carrier_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    carrier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[DealStatus] = mapped_column(SAEnum(DealStatus), default=DealStatus.draft)
    # T3.7 — set when the vault is sealed (deal closed). While set,
    # `append_deal_event` refuses everything except `dispute_opened`
    # (which unseals). Re-sealed on dispute resolution that closes the deal.
    sealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # T3.11.23 — the chat this deal is nested in (owner's model 2026-09-07).
    # One chat per person, many deals inside it.
    #
    # Nullable only for rows that predate the chat; every new deal has one, and
    # a deal without a chat is a conversation with nowhere to happen.
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chats.id"), nullable=True, index=True
    )
    # T3.11.23 — the number people say out loud (owner's request 2026-09-07:
    # «должно быть понятно какая сделка для чего — название, цена, номер
    # отправки»). A UUID is neither dictated nor pasted into a message.
    #
    # **Random, not sequential.** A counter publishes how many deals the
    # platform has ever had, to every user, forever — and for a young
    # marketplace that is a number to keep. Generated in `core.shipment_no`,
    # which also drops the characters that get misread aloud.
    shipment_no: Mapped[str | None] = mapped_column(
        String(12), unique=True, nullable=True, index=True
    )
    # T3.11.27 — who is editing the agreement right now, and until when.
    #
    # Owner's rule 2026-09-07: «две минуты — это окно для правки, пока другой
    # ждёт; если справился раньше — молодец, нет — запускай ещё раз». The hold is
    # taken **before** the change and released by it, which is the opposite of
    # what a first attempt did: it started the window at submission, so every
    # proposal froze the other side for two minutes exactly when they were meant
    # to answer it.
    #
    # Two columns on the deal rather than a table: a hold is one fact about one
    # deal, it never needs history, and it expires by comparison rather than by
    # a sweeper.
    edit_hold_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    edit_hold_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealEvent(Base):
    """T3.6 — every row is a link in its deal's tamper-evident hash chain.

    `seq`/`entry_hash`/`prev_hash` are NOT NULL and assigned exclusively by
    `app.core.deal_chain.append_deal_event`. Constructing a `DealEvent` directly
    and adding it to the session fails at flush — that is deliberate: an
    unchained event would be a hole in the arbitration record, and a loud
    IntegrityError beats a silent gap.
    """

    __tablename__ = "deal_events"
    __table_args__ = (
        UniqueConstraint("deal_id", "seq", name="uq_deal_events_deal_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    event_type: Mapped[DealEventType] = mapped_column(SAEnum(DealEventType))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    nostr_sig: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nostr_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nostr_created_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nostr_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Chain position within the deal, starting at 1. Gapless and monotonic.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    # NULL for a deal's first entry (hashed as deal_chain.GENESIS_HASH).
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealChainAnchor(Base):
    """T3.6 — a chain head published to third-party Nostr relays.

    The hash chain proves nobody edited the log *behind our back*; it cannot
    prove we did not rewrite it ourselves, since we assign `seq`. Publishing the
    head to relays we do not control, signed by the platform key, puts someone
    else's timestamp on it — after which the history behind that head is fixed.

    One row per successfully published head. Rows are only written when at least
    one relay accepted the event, so an unpublished head is simply retried on
    the next tick.
    """

    __tablename__ = "deal_chain_anchors"
    __table_args__ = (
        UniqueConstraint("deal_id", "seq", name="uq_deal_chain_anchors_deal_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"), index=True)
    # Chain head at anchoring time: everything up to and including this seq is
    # covered by `entry_hash`.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    nostr_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    nostr_pubkey: Mapped[str] = mapped_column(String(64), nullable=False)
    # T3.7 — anchoring backend this row was published through. Only 'nostr' is
    # implemented; 'ipfs' / 'ots' are reserved so new backends are a row-writer
    # away, not a schema migration (D-DVLT-PROTOCOL).
    backend: Mapped[str] = mapped_column(
        String(16), nullable=False, default="nostr", server_default="nostr"
    )
    # {relay_url: accepted} as reported by the relays at publish time.
    relays: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DealVaultMessage(Base):
    __tablename__ = "deal_vault_messages"
    # Chat read: filter by deal, order by (created_at, id) — one range scan
    # instead of scan + sort (T_PERF.1, 0034).
    __table_args__ = (
        Index("ix_deal_vault_messages_deal_created", "deal_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # T1.21: text is stored AES-256-GCM encrypted. `text` property below wraps
    # these two columns so callers keep using `msg.text` transparently.
    text_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    text_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # T3.34 — the envelope. Deliberately plain columns and NOT encrypted: the
    # server has to read them to validate a transition, decide who still owes an
    # answer, and drive reminders. The sensitive part of a card stays in `text`,
    # which is encrypted exactly as before.
    #
    # `card_kind` is a plain string rather than a DB enum on purpose. The
    # catalogue grows with every task from T3.35 to T3.39, and a DB enum would
    # turn each new card type into a migration. Validation lives in
    # `app.core.cards.CardKind`, where adding a member costs nothing.
    card_kind: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    card_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    card_state: Mapped[CardState | None] = mapped_column(
        SAEnum(CardState), nullable=True
    )
    requires_ack_by: Mapped[CardAckRole | None] = mapped_column(
        SAEnum(CardAckRole), nullable=True
    )
    acked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deal_vault_messages.id"), nullable=True
    )
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
    # T3.11.24 — nullable, because a recipient chosen from contacts was never
    # invited: the sender named an account that already exists and the row is
    # written accepted. Minting a token nobody will ever send would have been a
    # live credential kept for the sake of a NOT NULL, and a column that lies
    # about how this participant got here.
    invite_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
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


class UserFile(Base):
    """T3.11.25 — a file belongs to the person, not to the deal it first went to.

    Owner's statement 2026-09-07: «файлы из одной сделки с этим аккаунтом
    доступны и для новых сделок». Until now an `Attachment` hung off a
    `message_id` and nowhere else, so somebody who had sent their passport once
    sent it again for the next parcel, and the two copies were unrelated bytes
    as far as the platform could tell.

    **One row per (owner, hash).** The same document uploaded twice is one file
    in the safe: the hash is what identifies it, and keeping two rows would make
    «впервые предоставлен» a question with two answers.

    The safe holds the *reference*, never a second copy of the bytes: `r2_key`
    is the object already stored for the first attachment, and re-attaching
    points a new `Attachment` at the same key.
    """

    __tablename__ = "user_files"
    __table_args__ = (
        UniqueConstraint("owner_id", "file_hash", name="uq_user_files_owner_hash"),
        Index("ix_user_files_owner", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    r2_key: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[AttachmentKind] = mapped_column(SAEnum(AttachmentKind))
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # Copied from the attachment that first carried these bytes. Kept here too
    # because the safe is browsed on its own: a file listed without what we know
    # about it would be a file people re-send blind.
    scan_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="pending", server_default="pending"
    )
    # T3.11.25 — «паспорт, впервые предоставлен 3 марта». This is that date, and
    # it never moves: re-attaching writes a new event, not a new first time.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Attachment(Base):
    __tablename__ = "attachments"
    # `selectinload(...attachments)` fetches a whole chat page by message id
    # (T_PERF.1, 0034).
    __table_args__ = (Index("ix_attachments_message_id", "message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deal_vault_messages.id"))
    # T3.11.25 — the file in the owner's safe these bytes belong to. Nullable
    # for every attachment uploaded before the safe existed: those rows are not
    # wrong, they simply predate the question.
    user_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_files.id"), nullable=True, index=True
    )
    r2_key: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64))
    ipfs_cid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[AttachmentKind] = mapped_column(SAEnum(AttachmentKind))
    # T3.8 — what we actually know about these bytes: `pending` | `clean` |
    # `infected`. `pending` is not a synonym for safe; it means nobody has
    # looked. Owner's decision 2026-08-02: an unreachable scanner queues the
    # file rather than refusing the upload, so this column is the difference
    # between "we scan uploads" and "we scanned this upload".
    scan_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="pending", server_default="pending"
    )
    scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    message: Mapped["DealVaultMessage"] = relationship("DealVaultMessage", back_populates="attachments", lazy="raise")
