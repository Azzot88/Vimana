"""T_SEC.5 — a way back for an account that has a password and forgot it.

Until now the only recovery was a set of codes the user had to have created on
purpose, through a step-up ceremony nobody is pushed towards. Someone who
registered with an email and a password and forgot it had no path at all — and
the product meanwhile told them, in the confirmation letter and in the banner,
that "access comes back through this address". This closes the gap between the
promise and the mechanism.

The token is stored as a hash, like a password and like the email confirmation
code: the platform must not be able to read a live reset token out of its own
database, because a backup or a rogue query would then be an account takeover
kit for every pending reset.

No index. The lookup is by user (found via the identifier) and the column is
read once per reset.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-09
"""
from alembic import op


revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "password_reset_hash VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "password_reset_expires_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_expires_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_hash")
