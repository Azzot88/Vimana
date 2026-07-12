"""Role-based access control: single `role` column (T1.24 pt.1)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-11

Replaces `is_superuser` + `is_arbiter` booleans with a single `role` column.
Values: 'user' | 'arbiter' | 'superuser'. Permissions are derived in Python
from role + self-service capabilities (see app/core/permissions.py).
Idempotent — safe to re-run.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) "
        "NOT NULL DEFAULT 'user'"
    )

    # Backfill from legacy booleans if they exist. Superuser wins over arbiter.
    has_superuser = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'is_superuser'"
        )
    ).fetchone()
    has_arbiter = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'is_arbiter'"
        )
    ).fetchone()

    if has_arbiter:
        op.execute(
            "UPDATE users SET role = 'arbiter' "
            "WHERE is_arbiter = true AND role = 'user'"
        )
    if has_superuser:
        op.execute(
            "UPDATE users SET role = 'superuser' "
            "WHERE is_superuser = true"
        )
        op.execute("ALTER TABLE users DROP COLUMN is_superuser")
    if has_arbiter:
        op.execute("ALTER TABLE users DROP COLUMN is_arbiter")

    # Promote User Zero if not already (fallback if migration 0006 ran before
    # the user was registered).
    op.execute(
        "UPDATE users SET role = 'superuser' "
        "WHERE email = 'nyxter@dealvault.club' AND role <> 'superuser'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN "
        "NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_arbiter BOOLEAN "
        "NOT NULL DEFAULT false"
    )
    op.execute("UPDATE users SET is_superuser = (role = 'superuser')")
    op.execute("UPDATE users SET is_arbiter = (role IN ('arbiter', 'superuser'))")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS role")
