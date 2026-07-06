"""waitlist entries

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waitlist",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_waitlist_email"),
    )
    op.create_index("ix_waitlist_email", "waitlist", ["email"])


def downgrade() -> None:
    op.drop_index("ix_waitlist_email", table_name="waitlist")
    op.drop_table("waitlist")
