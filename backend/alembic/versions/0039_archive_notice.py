"""T3.19 — the 15-day window after an identity is retired.

Two columns: whether the owner has been *told*, and what they *chose*.

The choice is not derived from `public_profile`. Setting that to `hidden` while
the key was alive is an ordinary preference the account may revisit; closing the
archive is final. Storing one as the other would make a reversible decision
irreversible the moment the key was lost — and the owner would never have been
asked.

The window is arithmetic on `key_lost_at`, not a stored deadline: a column would
be a second truth about a date we already have, and would drift the moment
anyone edited either one.

Default asymmetry, stated so it is not mistaken for an oversight: doing nothing
leaves the archive visible, choosing "no" closes it for good. An accidental "no"
costs privacy, accidental silence costs nothing for fifteen days. Only the safe
side is irreversible.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-01
"""
from alembic import op


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS archive_notice_seen_at TIMESTAMPTZ"
    )
    # NULL = not chosen. No server default: "the owner said nothing" and "the
    # owner asked for it" are different states, and only the first may still
    # change into the second.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS archive_choice VARCHAR(8)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS archive_notice_seen_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS archive_choice")
