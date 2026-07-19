"""T_UX.2 — Route notes + platform disclaimers (informational, not blocking).

Position D-COMPLIANCE-STANCE in TECHSTATE: Vimana does NOT block route pairs.
Notes surface known specifics of a corridor (attention / complex / restricted);
the user decides. Platform-wide notices ("Vimana не проверяет содержимое
посылок") sit as always-visible disclaimers.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RouteStatus(str, enum.Enum):
    standard = "standard"
    attention = "attention"
    complex = "complex"
    restricted = "restricted"


class NoticeSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    alert = "alert"


class NoticeSurface(str, enum.Enum):
    footer = "footer"
    trip_card = "trip_card"
    deal_page = "deal_page"
    all = "all"


class RouteNote(Base):
    """Per-corridor informational notice. Wildcards `*` in origin/destination
    are supported (`*→IR` = все в Иран)."""

    __tablename__ = "route_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    origin_iso: Mapped[str] = mapped_column(String(3), index=True)  # ISO-3166 alpha-2/3 or '*'
    destination_iso: Mapped[str] = mapped_column(String(3), index=True)
    status: Mapped[RouteStatus] = mapped_column(
        SAEnum(RouteStatus), default=RouteStatus.standard
    )
    severity: Mapped[NoticeSeverity] = mapped_column(
        SAEnum(NoticeSeverity), default=NoticeSeverity.info
    )
    headline: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    active_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    active_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlatformNotice(Base):
    """Global always-visible disclaimer. `key` is a stable slug for referring
    to a notice in code / analytics; `headline` + `body` hold the user-facing
    text edited by the platform owner."""

    __tablename__ = "platform_notices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    severity: Mapped[NoticeSeverity] = mapped_column(
        SAEnum(NoticeSeverity), default=NoticeSeverity.info
    )
    target_surface: Mapped[NoticeSurface] = mapped_column(
        SAEnum(NoticeSurface), default=NoticeSurface.all
    )
    headline: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    active_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    active_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
