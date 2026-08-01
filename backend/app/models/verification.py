"""T2.1 — Peer Identity Verification models.

Container encryption: AES-256-GCM. Key = owner's Nostr nsec (first 32 bytes).
Only custodial users can upload in MVP (self-custody users get 422 because
the server can't decrypt on their behalf without their client-side key).

Escalation: creates `Dispute` (from T1.23) with reason='identity_fraud'.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VerificationLevel(str, enum.Enum):
    auto = "auto"  # local OCR + public sanctions CSV
    peer = "peer"  # another user visually / photographically confirmed
    kyc = "kyc"  # regulatory provider (Phase 4)


class VerificationRequestStatus(str, enum.Enum):
    pending = "pending"
    later_in_person = "later_in_person"
    declined = "declined"  # sender's refusal — badge on profile
    declined_polite = "declined_polite"  # carrier's refusal — no consequences
    verified = "verified"
    escalated = "escalated"


class VerificationTargetRole(str, enum.Enum):
    sender = "sender"
    carrier = "carrier"


class SanctionsStatus(str, enum.Enum):
    clean = "clean"
    match = "match"
    review_needed = "review_needed"


class OwnerRole(str, enum.Enum):
    sender = "sender"
    carrier = "carrier"
    both = "both"


class StorageMode(str, enum.Enum):
    encrypted_blob = "encrypted_blob"  # T2.1 MVP
    zk_snark = "zk_snark"  # T6.4 — future


class VerificationSource(str, enum.Enum):
    auto_ocr = "auto_ocr"
    peer = "peer"
    arbiter_review = "arbiter_review"
    kyc_provider = "kyc_provider"


class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    # Requests are always listed per deal (T_PERF.1, 0034).
    __table_args__ = (Index("ix_verification_requests_deal_id", "deal_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    requested_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    target_role: Mapped[VerificationTargetRole] = mapped_column(
        SAEnum(VerificationTargetRole)
    )
    status: Mapped[VerificationRequestStatus] = mapped_column(
        SAEnum(VerificationRequestStatus),
        default=VerificationRequestStatus.pending,
        server_default=VerificationRequestStatus.pending.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IdentityContainer(Base):
    __tablename__ = "identity_containers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    owner_role: Mapped[OwnerRole] = mapped_column(
        SAEnum(OwnerRole), default=OwnerRole.both, server_default=OwnerRole.both.value
    )
    storage_mode: Mapped[StorageMode] = mapped_column(
        SAEnum(StorageMode),
        default=StorageMode.encrypted_blob,
        server_default=StorageMode.encrypted_blob.value,
    )
    blob_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    blob_nonce: Mapped[bytes] = mapped_column(LargeBinary)  # 12 bytes for AES-GCM
    # T3.12 pt.2b — set once the owner takes their own key. When present, the
    # blob is under a random content key wrapped NIP-04 to the owner; when NULL,
    # the legacy scheme applies (AES key = owner's nsec). The sender pubkey is
    # required because NIP-04 is ECDH: the reader needs the other half.
    key_envelope: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_envelope_sender_pubkey: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    doc_hash: Mapped[str] = mapped_column(String(64))  # sha256 of raw doc bytes
    doc_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sanctions_check_status: Mapped[SanctionsStatus] = mapped_column(
        SAEnum(SanctionsStatus),
        default=SanctionsStatus.clean,
        server_default=SanctionsStatus.clean.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VerificationBadge(Base):
    """Append-only trust event. Aggregation lives in `User.highest_verification_level`."""

    __tablename__ = "verification_badges"
    # Read per user on profiles, trip cards and the hourly UBA recompute
    # (T_PERF.1, 0034).
    __table_args__ = (Index("ix_verification_badges_subject_id", "subject_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    level: Mapped[VerificationLevel] = mapped_column(SAEnum(VerificationLevel))
    source: Mapped[VerificationSource] = mapped_column(SAEnum(VerificationSource))
    container_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity_containers.id"), nullable=True
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    in_deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deals.id"), nullable=True
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SanctionsList(Base):
    """OFAC SDN + EU consolidated (populated by Celery beat in a follow-up task).

    Empty in T2.1 MVP — sanctions_check_status defaults to 'clean' until wiring is done.
    """

    __tablename__ = "sanctions_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32))
    name_normalized: Mapped[str] = mapped_column(String(255), index=True)
    dob: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
