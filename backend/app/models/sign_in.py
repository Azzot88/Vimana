"""T_SEC.6 — the devices an account has already been entered from.

To say a device is new one has to remember the old ones, and this is the whole
of that memory. Deliberately not a session table: it holds no token, grants
nothing, and cannot be used to sign anyone in or out.

**What is stored is a description, not an identifier.** No raw address, no raw
`User-Agent` — a `/24` network, a browser-and-OS label, and a hash of the two.
The hash is what the comparison runs on; the other two columns exist so the
letter can say something a person recognises. Sign-in history is a category of
personal data the product did not hold before, and holding the smallest thing
that answers the question is the price of starting to hold it at all.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Rows older than this are deleted (`tasks/cleanup.purge_old_sign_ins`). A
# device unused for three months coming back **should** raise the letter again:
# the record has expired, and so has the assumption that it is still the same
# hands.
RETENTION_DAYS = 90


class UserSignIn(Base):
    """One device-and-network an account has been entered from before."""

    __tablename__ = "user_sign_ins"
    __table_args__ = (
        # Declared here as well as in migration 0046 so that `create_all` — the
        # way the test database is built — produces the same table the server
        # runs on. The uniqueness is the mechanism, not a nicety: it is what
        # makes two simultaneous sign-ins from one new device send one letter.
        UniqueConstraint("user_id", "fingerprint", name="uq_user_sign_ins_device"),
        Index("ix_user_sign_ins_last_seen", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # sha256 over (browser family, OS family, network). Fixed width, and it is
    # the only column any comparison touches.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Kept for the letter, which has to name something the reader can check
    # against their own day. "Chrome on macOS" is that; a hash is not.
    device: Mapped[str] = mapped_column(String(120), nullable=False)
    network: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
