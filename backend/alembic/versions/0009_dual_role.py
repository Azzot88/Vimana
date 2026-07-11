"""Dual role: can_carry, can_send, active_mode; drop is_carrier (T1.24)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-11

Everyone can both carry and send by default. `active_mode` is a UI preference
('sender' or 'carrier'), authorization is by capability (`can_carry`/`can_send`).
Idempotent — safe to re-run.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_carry BOOLEAN "
        "NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_send BOOLEAN "
        "NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_mode VARCHAR(10) "
        "NOT NULL DEFAULT 'sender'"
    )

    # Backfill from is_carrier if the legacy column still exists.
    has_is_carrier = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'is_carrier'"
        )
    ).fetchone()
    if has_is_carrier:
        # Preserve intent: someone who registered as carrier keeps carrier mode
        # and can_carry=true; can_send stays true (everyone can send).
        op.execute(
            "UPDATE users SET can_carry = is_carrier, "
            "active_mode = CASE WHEN is_carrier THEN 'carrier' ELSE 'sender' END "
            "WHERE active_mode = 'sender'"
        )
        op.execute("ALTER TABLE users DROP COLUMN is_carrier")


def downgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_carrier BOOLEAN NOT NULL DEFAULT false")
    op.execute("UPDATE users SET is_carrier = (active_mode = 'carrier')")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS active_mode")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS can_send")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS can_carry")
