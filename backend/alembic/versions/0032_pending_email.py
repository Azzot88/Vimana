"""T3.15 — changing the account's email address, proved before it lands.

One column, not a second copy of the verification machinery. The invariant is
"at most one address is awaiting proof at a time", so the existing
`email_verification_*` columns keep meaning what they meant — they just refer
to `pending_email` when one is set, and to `email` otherwise.

The old address stays live and verified the whole time. That is the point: a
mistyped new address costs a retry instead of the recovery channel, and a
session that was stolen cannot redirect account recovery without also reading
the new mailbox.

No UNIQUE constraint here on purpose. A pending claim is not a reservation:
several accounts may name the same address, and whoever confirms first takes
it — the unique index on `users.email` decides that at swap time. Holding a
reservation instead would let anyone park someone else's address indefinitely.

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-30
"""
from alembic import op


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_email VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS pending_email")
