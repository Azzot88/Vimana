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


class MeetingPlace(Base):
    """T3.11.07 — where this person is willing to meet, in their own words.

    Deliberately *not* an address. An address is a place a parcel is sent to and
    has the structure the post office needs; a meeting place is «у метро Фили,
    у выхода №3» or «Terminal D, departures, by the Costa» — a sentence one
    human says to another, and any attempt to reduce it to country/city/street
    would either refuse it or throw away the half that matters.

    T3.11.07 (owner's decision 2026-09-06) — the country and the city sit
    **beside** that sentence, not instead of it. The trip form offers meeting
    places for one end of a route, and without a country it was offering a
    Moscow landmark to somebody arriving in Dubai: a list that has to be read
    and rejected on every publication is worse than no list. The description
    stays free text and stays the point; these two are the keys it is filed
    under.

    `country_iso` is nullable only because rows exist that predate it — the
    schema requires it on every new one. A place whose country is unknown is
    offered on every route, which is the honest reading of «not stated» and the
    behaviour those rows already had.

    A list with one default, like the addresses above and for the same reason:
    a carrier meets people in two or three usual spots, and picking one per trip
    is a choice, not a form to fill in again.

    Owner's decision 2026-09-06.
    """

    __tablename__ = "meeting_places"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Long enough for a sentence with landmarks, short enough not to become a
    # second free-text field for carriage rules.
    description: Mapped[str] = mapped_column(String(300))
    country_iso: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # The city matters here and not on the payment methods: «у метро Фили» is
    # only findable if you know it is Moscow, and one carrier meets people in
    # two cities of one country often enough for the country alone to be too
    # coarse a filter.
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_meeting_places_user_default",
            "user_id",
            unique=True,
            postgresql_where=(is_default.is_(True)),
        ),
    )
