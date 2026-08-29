"""T3.42 — where a role came from, kept as a journal rather than a column.

The role column said what somebody may do and never said why. For an arbiter that
gap is the sharp one: the arbiter opens a deal's vault through an
`OperatorAccessGrant` (T3.2), and **every one of those reads is written into the
chain** — so the record of the power being *used* is immutable, while the record
of where the power came from did not exist at all.

Three properties, and each is a refusal of the obvious shortcut.

**A change appends, it never edits.** Same shape as `PlatformParameter` (T3.40),
for the same reason: "who made this person an arbiter, and when" has to be
answerable from the table rather than from somebody's memory. An UPDATE would
make the current state readable and its origin unknowable.

**Revocation is an event too.** Written down separately because it is the half
that gets lost: an appointment is remembered, a withdrawal is not. A journal
that records only grants describes a platform where nobody's power ever ends.

**The offer is not the role.** An `offered` row changes nothing about what the
account may do — `users.roles` is untouched until the person accepts. That is why
the permission layer needs no new logic at all: an unaccepted offer is invisible
to `perms_of` because there is nothing there to see. The alternative — a role
column plus an `is_confirmed` flag — makes acceptance a decoration painted over
access that was already granted.

`users.roles` therefore stays the single answer to "what may this account do",
and this table is the single answer to "how did it come to be that way". The
invariant tying them together: **every change of `users.roles` writes a row
here**, and nothing else may write that column.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RoleGrantEvent(str, enum.Enum):
    """What happened. The state of a (subject, role) pair is its latest row.

    `revoked` covers both withdrawing a live role and taking back an offer
    nobody answered yet. They are not distinguished because the journal already
    shows which one it was: the row before it says `accepted` or `offered`, and
    inventing a fifth name for something the sequence states is a vocabulary
    that has to be kept in sync with reality.
    """

    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    revoked = "revoked"


class RoleGrant(Base):
    """One event in the life of one role for one account. Append-only."""

    __tablename__ = "role_grants"
    __table_args__ = (
        # The two questions asked of this table: "what is the state of this
        # role for this person" (latest row for the pair) and "show me this
        # person's history" (all rows, newest first).
        Index("ix_role_grants_subject_role", "subject_id", "role", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # The role value as it appears in `users.roles` — `arbiter`,
    # `compliance_editor`. A string rather than an enum column because the set
    # of roles lives in `core.permissions.Role` and is validated there; two
    # declarations of the same list drift, and the one in the database is the
    # one nobody remembers to migrate.
    role: Mapped[str] = mapped_column(String(32))
    event: Mapped[RoleGrantEvent] = mapped_column(SAEnum(RoleGrantEvent))
    # Who did it. Null for `accepted` / `declined`, where the actor is the
    # subject and saying so twice invites the two to disagree.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Why. An audit without a reason is a log — the same argument that put
    # `comment` on `PlatformParameter`.
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
