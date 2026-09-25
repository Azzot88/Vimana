"""T_UX.29 pt.7 — what happened while you were not looking.

Owner, 2026-09-20: «В панели оповещений должны появляться статусы… Панель
должна показывать обновления, произошедшие за период неактивности. Если
изменения произошли в активном окне, их статусы показывать не нужно.»

That last sentence is the whole design. A notification is not a copy of every
event — it is the answer to «что я пропустил», and an event somebody watched
happen is not something they missed. So the row is written for every notifiable
act, and the screen that **showed** it marks it read on the spot: the deal
page clears its own deal's notifications while it is open and visible. What is
left in the bell is, by construction, what nobody saw.

Rows rather than a counter on the user: a counter answers «сколько» and nothing
else, and the panel has to say what each one was and take you there.

**Not part of the deal chain.** A notification is a courtesy, not evidence —
deleting one changes nothing about what happened, because what happened is the
card in the vault. Keeping it out of the append-only side is deliberate: the
chain is what an arbiter reads, and it must not fill with records of who looked
at what.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class NotificationKind(str, enum.Enum):
    """What happened. Four, because the owner named four.

    Stored as a plain string rather than a PostgreSQL enum: this list will grow
    with every screen that learns to speak, and a new member of a database enum
    is a migration plus an `ALTER TYPE` that cannot run inside a transaction.
    The set of values a *client* must understand is small and versioned by the
    code that reads it; the column only has to keep the word.
    """

    #: A message somebody typed in a deal chat.
    chat_message = "chat.message"
    #: Somebody responded to a trip with cargo — a deal now exists.
    trip_response = "trip.response"
    #: A sender is asking a corridor for a carrier.
    request_new = "request.new"
    #: A card was raised or answered on a deal: the status moved.
    deal_status = "deal.status"
    #: T_UX.31 — a trip was published into a corridor this person asked about.
    #: The letter existed since T3.11.19; the bell did not.
    corridor_trip = "trip.corridor"
    #: T_UX.31 — somebody offered this person the role of recipient. Not tied to
    #: the deal: until the offer is accepted the deal is not theirs to open.
    recipient_offer = "recipient.offer"
    #: T_UX.31 — the pool picked this arbiter for a dispute; 24 hours to answer.
    dispute_offer = "dispute.offer"


class Notification(Base):
    """One thing that happened, addressed to one person.

    Addressed, not broadcast: a deal has three people in it and each of them
    needs their own read state. Fanning out at write time costs three rows and
    buys a `read_at` that means something; a shared row with a join table would
    be the same storage and a harder question.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    #: The deal or the trip this is about, so the panel can take somebody there
    #: and the deal screen can clear its own. Both nullable: a corridor request
    #: belongs to neither.
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=True
    )
    #: What to print, as data the client turns into a sentence in its own
    #: language: a route, a status word, a name. **Never the text of a message**
    #: — chat bodies are encrypted at rest and an unencrypted copy here would
    #: undo that for the price of a nicer preview.
    payload: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # The two questions this table is asked: «что у меня непрочитано» and
        # «покажи ленту». Both are per-user and newest-first.
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # Literal predicate, not `read_at.is_(None)`: inside the class body the
        # attribute is still a `MappedColumn`, not a column expression.
        Index(
            "ix_notifications_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )


class PushSubscription(Base):
    """T_UX.29 pt.7 — «надо заложить основу для пуш-уведомлений» (owner).

    A Web Push endpoint belongs to a **browser on a device**, not to a person:
    the same account signed in on a laptop and a phone has two, and revoking one
    must not silence the other. So the endpoint URL is the identity of the row,
    unique on its own — the browser hands out one per subscription and re-issues
    it when it rotates.

    **Nothing sends to these yet, and that is the point of the seam.** The rows
    can be collected from the day the button exists, so that turning delivery on
    later is a worker task and a pair of VAPID keys rather than a migration plus
    a consent flow nobody has given yet. `core.notify.notify` is where the fan-out
    will hang: it already writes the row and publishes the live event, and push
    is the third thing it will do.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    #: The browser's public key and auth secret, as the Push API hands them over.
    #: Opaque to us and useless without the private VAPID key we do not have yet.
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
    )
