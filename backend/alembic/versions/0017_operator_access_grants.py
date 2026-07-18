"""OperatorAccessGrant (T3.2)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'operator_access_grants'"
        )
    ).fetchone()
    if not exists:
        op.execute(
            """
            CREATE TABLE operator_access_grants (
                id UUID PRIMARY KEY,
                dispute_id UUID NOT NULL REFERENCES disputes(id),
                granted_by UUID NOT NULL REFERENCES users(id),
                granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMPTZ,
                CONSTRAINT uq_grant_dispute_party UNIQUE (dispute_id, granted_by)
            )
            """
        )
        op.execute(
            "CREATE INDEX idx_grants_dispute_active "
            "ON operator_access_grants(dispute_id) WHERE revoked_at IS NULL"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operator_access_grants")
