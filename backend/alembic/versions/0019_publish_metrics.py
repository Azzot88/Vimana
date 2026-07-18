"""publish_metrics table (T3.5 pt.2)

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='publish_metrics'"
        )
    ).fetchone()
    if not exists:
        op.execute(
            """
            CREATE TABLE publish_metrics (
                id UUID PRIMARY KEY,
                success_count BIGINT NOT NULL DEFAULT 0,
                error_count BIGINT NOT NULL DEFAULT 0,
                last_attempt_at TIMESTAMPTZ
            )
            """
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS publish_metrics")
