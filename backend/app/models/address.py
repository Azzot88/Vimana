"""T_UX.4 — multiple named receiving addresses per user.

Users hold a list of labelled addresses ("Home", "Office", "Mom's place")
and pick which one to share in each deal chat. The legacy `User.receiving_*`
columns stay populated until the next cleanup migration; new code should
read from `ReceivingAddress` first, fall back to the legacy fields only
during backfill.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReceivingAddress(Base):
    __tablename__ = "receiving_addresses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(60))
    country_iso: Mapped[str] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city_geoname_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        # Partial unique — at most one default row per user.
        Index(
            "uq_receiving_addresses_user_default",
            "user_id",
            unique=True,
            postgresql_where=(is_default.is_(True)),
        ),
    )
