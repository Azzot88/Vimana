"""users.avatar_key (T_UX.4 B follow-up).

Just a nullable R2 object key. Presigned URL is minted per response, never
stored.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-20
"""
from alembic import op


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_key VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS avatar_key")
