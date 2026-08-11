"""T_SEC.6 — remember the devices an account has been entered from.

The table exists so that "this device is new" is a fact rather than a guess.
It stores a hash, a /24 and a browser-and-OS label — no address, no agent
string. See `models/sign_in` for why the grain is that coarse.

`UNIQUE (user_id, fingerprint)` is the point of the table, not a detail: two
sign-ins arriving together on the same new device must produce one row and
therefore one letter.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-11
"""
from alembic import op


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sign_ins (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            fingerprint VARCHAR(64) NOT NULL,
            device VARCHAR(120) NOT NULL,
            network VARCHAR(64) NOT NULL,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_sign_ins_device "
        "ON user_sign_ins (user_id, fingerprint)"
    )
    # The retention sweep deletes by age across all users; without this it is a
    # sequential scan of the whole table every night.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_sign_ins_last_seen "
        "ON user_sign_ins (last_seen_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_sign_ins")
