import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class InviteLink(Base):
    __tablename__ = "invite_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Connection(Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("user_id", "connected_user_id", name="uq_connections_user_connected"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    connected_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    invite_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # T3.12.06 — the row is a contact and nothing more: one-way, «просто
    # знакомые». Closeness moved out to `ClosePair` (`0095`); the `tier` that
    # used to live here is gone.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    connected_user: Mapped["User"] = relationship(
        "User", foreign_keys=[connected_user_id], lazy="raise"
    )


class ClosePair(Base):
    """T3.12.06 — two people close to each other, as a thing of its own.

    Owner (`IMPLEMENTATIONPLAN §3.12.3` п. 6; answers 2026-09-14): contacts are a
    one-way list, and closeness is a different mechanism — **asked and
    accepted**. It used to be a `tier` on each directed contact row, the pair
    close when both rows happened to say so: a coincidence of two settings
    rather than an answer one person gave another. Now one asks, the other
    accepts or declines, and either of them can end it.

    Asked only of somebody already in the asker's contacts (owner, 2026-09-14).

    One row per request. A pair has at most one **open** row — pending or
    accepted — whoever asked (`uq_close_pairs_open`, over the unordered pair). A
    declined or ended row stays as the record; asking again is a new row.
    """

    __tablename__ = "close_pairs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    addressee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


Index(
    "uq_close_pairs_open",
    func.least(ClosePair.requester_id, ClosePair.addressee_id),
    func.greatest(ClosePair.requester_id, ClosePair.addressee_id),
    unique=True,
    postgresql_where=text("declined_at IS NULL AND ended_at IS NULL"),
)
