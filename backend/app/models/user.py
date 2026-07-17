import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    # T1.24 dual role: capability flags (can this user do X?) + active UI mode.
    # Everyone can both carry and send by default — mode is a UI preference,
    # authorization is by capability. `active_mode` ∈ {'sender', 'carrier'}.
    can_carry: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    can_send: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    active_mode: Mapped[str] = mapped_column(String(10), default="sender", server_default="sender")
    nostr_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # T2.2 — custodial nsec (AES-256-GCM). Deleted when user claims self-custody.
    nsec_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    nsec_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_self_custody: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
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

    # T1.26 — private receiving address. Never exposed in list-endpoints or via
    # any UserOut except /me. Sharing into a chat is an explicit user action.
    receiving_country_iso: Mapped[str | None] = mapped_column(String(2), nullable=True)
    receiving_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    receiving_city_geoname_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receiving_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receiving_postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    receiving_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
