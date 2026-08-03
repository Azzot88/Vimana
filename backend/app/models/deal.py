import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, JSON, LargeBinary, String, Text, UniqueConstraint, func
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
    # T3.7 — vault-content chain events: the chain covers messages/files/identity,
    # not just status transitions.
    message_added = "message_added"
    file_added = "file_added"
    sealed = "sealed"
    identity_ref = "identity_ref"


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
    # `selectinload(...attachments)` fetches a whole chat page by message id
    # (T_PERF.1, 0034).
    __table_args__ = (Index("ix_attachments_message_id", "message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deal_vault_messages.id"))
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
