"""T3.11.27 — how long a one-sided cancellation waits.

Owner's decision, 2026-09-07: cancelling before the handover has to be confirmed
by both sides, and a cancellation nobody answered closes itself — by this timeout
or at the flight's departure, whichever comes first.

**Both parties keep their own and the shorter applies.** The setting belongs to
whoever is in a hurry: a carrier flying tomorrow cannot wait a week for an
answer, and neither can a sender whose parcel is packed. Two columns would have
been one column and a rule about whose it is; one column on `users` and a `min()`
at the moment of cancelling is the same thing without the rule.

Hours rather than a duration string: the value is compared between two accounts,
added to a timestamp and printed as «сутки», and three readers of one string
would each parse it their own way.

48 as the starting value, not as a decision — the ceiling the owner named is a
week, and the number that turns out to be right will come from watching
cancellations rather than from this line.

Revision ID: 0080
Revises: 0079
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "cancel_timeout_hours",
            sa.Integer(),
            nullable=False,
            server_default="48",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "cancel_timeout_hours")
