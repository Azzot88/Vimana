import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
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
    # T3.11.24 — how close this person is, as *this* user sees it (owner's
    # definition 2026-09-07): «Контакты — просто знакомые… Близкие — те, кому
    # доверяешь».
    #
    # **The row is directed and the tier is directed with it.** A contact may be
    # one-way — you can keep someone in your list who has not kept you in
    # theirs, and that is the ordinary case for a carrier you liked. Closeness
    # cannot: a pair is close only when *both* rows say `close`, so this column
    # is one half of a claim and never the whole of it. `core.social.closeness`
    # is the only place that reads both halves; nothing else should ask a single
    # row whether two people are close, because a single row cannot know.
    tier: Mapped[str] = mapped_column(String(16), default="connection")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    connected_user: Mapped["User"] = relationship(
        "User", foreign_keys=[connected_user_id], lazy="raise"
    )
