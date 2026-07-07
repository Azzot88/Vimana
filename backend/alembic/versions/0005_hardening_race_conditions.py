"""hardening race conditions — unique connection pair

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-06
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dedupe potential duplicates before adding the constraint
    op.execute(
        """
        DELETE FROM connections a
        USING connections b
        WHERE a.id > b.id
          AND a.user_id = b.user_id
          AND a.connected_user_id = b.connected_user_id
        """
    )
    op.create_unique_constraint(
        "uq_connections_user_connected",
        "connections",
        ["user_id", "connected_user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_connections_user_connected", "connections", type_="unique")
