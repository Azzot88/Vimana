"""T3.25 — contacts and pending code exchanges.

Two tables that between them replace a growing column list on `users`, and the
fork of the confirmation logic that a second channel would otherwise require.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Kept as plain strings rather than a database enum: adding a channel should be
# a line here and a deploy, not a migration that locks the table.
CHANNELS = ("email", "sms", "whatsapp", "telegram")


class UserContact(Base):
    """One way to reach one account.

    Uniqueness is enforced only over **confirmed** rows (partial index in
    migration 0045). An unconfirmed row is a claim nobody has tested, and
    letting such a claim reserve a value would mean anyone could lock the real
    owner of a phone number out of the platform by typing it first.
    """

    __tablename__ = "user_contacts"
    __table_args__ = (Index("ix_user_contacts_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # T3.28 will let a contact be an identifier to sign in with. Recorded per
    # row rather than per channel: an account may keep a phone for delivery
    # only, and that is not the same thing as signing in with it.
    is_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def verified(self) -> bool:
        return self.verified_at is not None


class VerificationChallenge(Base):
    """A code in flight.

    `user_id` is nullable on purpose: at sign-up the code exists before the
    account does, and forcing a user here would mean creating an account for
    someone who has not yet proved they can read the address — which is exactly
    what the code is for.

    The code itself is never stored, only its hash: a leaked dump must not hand
    out working codes, the same rule the password and the reset token follow.
    """

    __tablename__ = "verification_challenges"
    __table_args__ = (Index("ix_verification_challenges_lookup", "channel", "value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(16), default="verify", server_default="verify"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
