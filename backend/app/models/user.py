import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, nullable=True)
    # T3.11 — nullable: accounts created via Nostr key or Passkey (T3.13/T3.14)
    # live without a password at all.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(100))
    # T1.24 dual role: capability flags (can this user do X?) + active UI mode.
    # Everyone can both carry and send by default — mode is a UI preference,
    # authorization is by capability. `active_mode` ∈ {'sender', 'carrier'}.
    can_carry: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    can_send: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    active_mode: Mapped[str] = mapped_column(String(10), default="sender", server_default="sender")
    # T3.12 — unique because the key IS the identity (D-KEY-IS-IDENTITY). Still
    # nullable: `core.service_keys.ensure_service_keys` backfills accounts that
    # predate T2.2 on startup, and NOT NULL waits for a follow-up migration once
    # prod shows none left.
    nostr_pubkey: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    # T2.2 — custodial nsec (AES-256-GCM). Deleted when user claims self-custody.
    nsec_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    nsec_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_self_custody: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # T3.12 — terminal state. Set only for an account whose *identity* key is
    # gone (self-custody). Losing the key is not losing access: a live passkey
    # still signs the user in, but they can no longer sign or read their own
    # encrypted history, and counterparties must see that.
    # T3.18 — `full` | `minimal` | `hidden`. Governs every public slice of this
    # account, not just the identity page: a setting that hides the page while
    # the numbers stay readable by direct request is a setting that lies.
    public_profile: Mapped[str] = mapped_column(
        String(16), default="full", server_default="full"
    )
    # T3.23 — the key this account used before the current one, and when it
    # stopped being current. Every `establish` swaps the key, so anything signed
    # earlier stays signed by a key the account no longer holds: valid and
    # verifiable, attached to an identifier that no longer answers. That is a
    # fact worth showing with its date rather than leaving people to notice it.
    # Public half only — the old private key was never ours to keep.
    previous_nostr_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identity_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # T3.21 — when the key was last handed to the browser for sealing into an
    # Identity Vault file. It is the only evidence the platform can honestly
    # have that a second copy exists: whether the user actually kept the file
    # is beyond our knowing, and pretending otherwise would put a claim in the
    # UI that nothing backs.
    identity_file_released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    key_lost_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # T3.19 — the retired identity's own say over its exhibit.
    # `archive_notice_seen_at`: the one-time notice was shown. A permanent modal
    # over a state that will never change is nagging, and gets closed unread.
    # `archive_choice`: NULL | 'show' | 'hide'. NULL means the owner has not
    # spoken; after ARCHIVE_WINDOW_DAYS that silence *becomes* 'show', which is
    # why the notice must name the date. 'hide' is final, and only 'hide' is:
    # a wrong "no" costs visibility, a wrong silence costs privacy but has
    # fifteen days of remedy. Only the safe side is irreversible.
    archive_notice_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archive_choice: Mapped[str | None] = mapped_column(String(8), nullable=True)
    business_activity_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Notifications
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notify_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telegram_link_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # T1.24 pt.1 — single role column, permissions derived via app.core.permissions.
    # Values: 'user' | 'arbiter' | 'superuser'. Superuser = User Zero.
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")

    # T2.1 — denormalized highest active VerificationBadge.level for fast reads.
    # Refreshed by app/core/verification.refresh_highest_level() after INSERT/revoke.
    highest_verification_level: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # T2.4 — denormalized Trust Graph counters. Refreshed by
    # app/core/trust.refresh_trust_counts() after edge INSERT/revoke.
    verifications_issued_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    verifications_received_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    dealt_with_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # T_UX.4 B — R2 object key for the user's avatar. Presigned URL is
    # generated on-the-fly, never stored.
    avatar_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # T3.11 — email ownership proof. The code is stored hashed (bcrypt), never
    # in the clear: a leaked dump must not hand out working codes. `attempts`
    # is per-issued-code and burns the code once it hits the cap.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verification_code_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verification_attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )
    email_verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # T3.15 — an address the user has asked to move to but has not proven yet.
    # The change lands only when a code sent *there* comes back, so `email`
    # keeps working as the recovery channel until the new one is real. A typo
    # therefore costs a retry, not the account; and a stolen session cannot
    # quietly redirect recovery mail without also reading the new mailbox.
    # Deliberately NOT unique: two people may have a pending claim on the same
    # address, and only the one who confirms first gets it — enforced by the
    # unique index on `email` at swap time, not by holding a reservation.
    pending_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # T3.15 — tokens issued before this moment are refused. Changing a password
    # sets it, which evicts every other session: the whole reason someone
    # changes a password in a hurry is that somebody else may be holding one,
    # and we never learn those tokens' `jti` to revoke them individually.
    # NULL means "nothing was ever retired" — the state every account starts in,
    # so deploying this does not sign anybody out.
    sessions_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def key_lost(self) -> bool:
        """Public signal — a dead identity must not look like a live one."""
        return self.key_lost_at is not None

    @property
    def identity_established(self) -> bool:
        """True once the user holds their own key. Until then `nostr_pubkey` is
        a service key the platform issued and still holds (T3.12)."""
        return self.key_self_custody

    @property
    def has_password(self) -> bool:
        """Whether a password exists at all — never the hash, never a hint.
        Drives the wording in the profile ('set' vs 'change') and nothing
        else."""
        return bool(self.password_hash)

    @property
    def email_verified(self) -> bool:
        """Derived flag for `MeOut`. An account without an email is not
        'unverified' — it simply has nothing to prove (T3.13/T3.14 paths)."""
        return self.email_verified_at is not None


class RecoveryCode(Base):
    """T3.16 — a spare way *in*, never a spare identity.

    One row per code, hashed the same way a password is: the platform can
    neither show a code again nor use one itself. Consuming a code proves
    possession of something the account holder wrote down, which is exactly the
    question step-up asks — so a code is accepted as a step-up proof rather than
    opening a parallel door beside it.

    What it restores depends on where the key lives (`D-KEY-TIERS`): on the
    lower rungs the platform still holds a copy, so a code brings back the
    account *and* the ability to read the vaults; once that copy is deleted a
    code brings back the account only, and the key comes back from the user's
    own Identity Vault file. Both sentences are true at once, which is why the
    UI text next to the codes has to follow the rung.
    """

    __tablename__ = "recovery_codes"
    __table_args__ = (
        Index("ix_recovery_codes_user_id", "user_id"),
        # The lookup the consume path walks: this account, this digest.
        Index("ix_recovery_codes_user_hash", "user_id", "code_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    code_hash: Mapped[str] = mapped_column(String(255))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
