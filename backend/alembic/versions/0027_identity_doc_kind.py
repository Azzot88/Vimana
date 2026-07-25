"""Attachment kind for identity-document copies in the deal vault (T3.9)

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-25
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction (0006 pattern).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE attachmentkind ADD VALUE IF NOT EXISTS 'identity_doc'")


def downgrade() -> None:
    # Postgres enum values cannot be removed; the extra value is harmless.
    pass
