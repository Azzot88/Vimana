"""T_UX.8 — record whether the waitlist confirmation letter was actually sent.

A waitlist entry until now was a row and nothing else: nobody was written to,
and nothing said so. This column is the difference between "we have not
answered this person yet" and "we answered and they did not reply".

Existing rows get NULL, which is the honest value — none of them were ever
answered. The consequence is intended: the backfill task reads exactly this
predicate and will pick up everyone who signed up before today.

No index. The table holds three rows, the query runs once by hand, and an
index would be ceremony around a sequential scan of a page.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-08
"""
from alembic import op


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS confirmation_sent_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE waitlist DROP COLUMN IF EXISTS confirmation_sent_at")
