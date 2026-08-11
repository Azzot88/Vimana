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

    T3.27 — **`code_hash` is nullable, and null means "opened, not yet minted".**
    Telegram runs backwards from every other channel: a bot cannot write to
    somebody who has never written to it, so the exchange starts with a link and
    the code exists only once the person presses Start. The row has to exist
    before that — otherwise the webhook could not tell a nonce we issued from a
    string a stranger typed — but there is no code in it yet, and storing a hash
    of something never sent would be a value that looks like a code and is not.
    """

    __tablename__ = "verification_challenges"
    __table_args__ = (Index("ix_verification_challenges_lookup", "channel", "value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # T3.27 — what the transport told us during the exchange, when we could not
    # know it up front. For a Telegram sign-in this is the chat id, learned at
    # `/start` and read back at `otp/verify` to resolve the account. Every other
    # channel leaves it null: there the caller names the target.
    resolved_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # T3.27 — and what the transport called them. An account born from an email
    # gets the local part of the address as a provisional name; a chat id has no
    # such part, and the welcome screen is skippable by design, so without this
    # a Telegram account could reach a counterparty with a blank name.
    resolved_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
