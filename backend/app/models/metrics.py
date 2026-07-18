"""T3.5 pt.2 — publish metrics model (single-row counter)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PublishMetric(Base):
    __tablename__ = "publish_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    success_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
