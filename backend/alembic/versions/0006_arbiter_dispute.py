"""User Zero + arbiter role + disputes

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("is_arbiter", sa.Boolean(), server_default="false", nullable=False),
    )

    # Extend the DealEventType enum (needs to be outside a transaction on some PG versions)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'dispute_opened'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'arbiter_opened'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'dispute_resolved'")

    dispute_status = sa.Enum("open", "claimed", "resolved", name="disputestatus")
    dispute_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "disputes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("deal_id", sa.UUID(as_uuid=True), sa.ForeignKey("deals.id"), nullable=False),
        sa.Column("opened_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("arbiter_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", dispute_status, server_default="open", nullable=False),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("deal_id", name="uq_disputes_deal_id"),
    )

    # Promote User Zero if present (idempotent)
    op.execute(
        "UPDATE users SET is_superuser = true WHERE email = 'nyxter@dealvault.club'"
    )


def downgrade() -> None:
    op.drop_table("disputes")
    sa.Enum(name="disputestatus").drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "is_arbiter")
    op.drop_column("users", "is_superuser")
