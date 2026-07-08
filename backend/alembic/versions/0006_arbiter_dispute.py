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
    # Idempotent column adds — retries after partial failure won't crash.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN "
        "NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_arbiter BOOLEAN "
        "NOT NULL DEFAULT false"
    )

    # Extend the DealEventType enum (needs to be outside a transaction on some PG versions)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'dispute_opened'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'arbiter_opened'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'dispute_resolved'")

    # Create the enum type explicitly; use create_type=False in the column below
    # so create_table doesn't try to re-CREATE it.
    dispute_status = sa.Enum("open", "claimed", "resolved", name="disputestatus")
    dispute_status.create(op.get_bind(), checkfirst=True)

    bind = op.get_bind()
    has_disputes = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'disputes'"
        )
    ).fetchone()
    if not has_disputes:
        op.create_table(
            "disputes",
            sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
            sa.Column("deal_id", sa.UUID(as_uuid=True), sa.ForeignKey("deals.id"), nullable=False),
            sa.Column("opened_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("arbiter_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "open", "claimed", "resolved",
                    name="disputestatus", create_type=False,
                ),
                server_default="open",
                nullable=False,
            ),
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
