"""T3.40 — business-logic parameters, versioned and corridor-scoped.

Every rate the platform charges used to be a constant in code: the carrier fee,
the escrow scale, the exposure multipliers, the minimum bond. That was tolerable
while there were three of them. There are a dozen now, and each one is money
belonging to somebody, so they move out of the source and behind an audited
screen.

Two properties are the whole point of the design:

**A change never edits a row.** It writes a new one with a later
`effective_from`. The old value stays readable, so "what was the fee on the day
this deal was struck" is answerable from the table rather than from git history.

**Scope is not decoration.** The minimum bond on UAE↔US and on an intra-European
route cannot be one number — different cargo values, different risk, different
carrier density. A parameter is looked up corridor-first, then global.

Deals do not read the table at settlement time. They read it once, at handoff,
and store the resolved version — MASTERPLAN §4.1. A rate changed today must not
reach back into a shipment already in the air.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

GLOBAL_SCOPE = "global"


class ParamValueType(str, enum.Enum):
    """How the stored string is meant to be read.

    Values live as text because the set spans rates, counts and thresholds, and
    a numeric column would force either a float (wrong for money) or a
    per-parameter table (wrong for a dozen rows).
    """

    percent = "percent"      # 3 -> 3%
    decimal = "decimal"      # 18.9, 0.75
    integer = "integer"      # 5000, 400
    string = "string"


class PlatformParameter(Base):
    """One version of one parameter, for one scope.

    The effective value for a key is the newest row whose `effective_from` has
    already passed, preferring a corridor-scoped row over the global one.
    """

    __tablename__ = "platform_parameters"
    __table_args__ = (
        # Resolution reads (key, scope) ordered by effective_from desc — one
        # range scan, no sort.
        Index(
            "ix_platform_parameters_key_scope_from",
            "key",
            "scope",
            "effective_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), index=True)
    # `global`, or a corridor written as `<ORIGIN_ISO>-><DEST_ISO>` (`AE->US`).
    scope: Mapped[str] = mapped_column(String(32), default=GLOBAL_SCOPE)
    value: Mapped[str] = mapped_column(String(128))
    value_type: Mapped[ParamValueType] = mapped_column(
        SAEnum(ParamValueType), default=ParamValueType.decimal
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Why the number changed. Audit without a reason is a log, not an audit.
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
