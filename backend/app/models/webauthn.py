"""T3.14 — a passkey is a device's key, not the user's identity.

Losing a phone deletes one row here. `users.nostr_pubkey` — the identity — is
untouched, and every other device keeps working. That separation is the reason
this table exists: "which device is at the keyboard" and "who is this person"
become independent questions.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    __table_args__ = (Index("ix_webauthn_credentials_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    # Globally unique, not per-user: login is usernameless (empty
    # `allowCredentials`), so this id is all the server gets and it has to
    # identify the account by itself.
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)

    # Authenticator's own counter. Compared on every login to spot a cloned
    # authenticator — but see `core/webauthn.py`: synced passkeys report 0
    # forever, so the check only applies once a non-zero count has been seen.
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    transports: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    aaguid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # False + usb/nfc transport means a hardware key that lives on one device
    # (YubiKey). True means the platform syncs it (iCloud, Google). Shown in the
    # UI because losing a synced key and losing a hardware key are different
    # events for the user.
    backed_up: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    uv_capable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
