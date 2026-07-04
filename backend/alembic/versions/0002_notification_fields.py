"""notification fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notify_email", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("notify_telegram", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("notify_whatsapp", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("telegram_link_token", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("whatsapp_number", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "whatsapp_number")
    op.drop_column("users", "telegram_link_token")
    op.drop_column("users", "telegram_chat_id")
    op.drop_column("users", "notify_whatsapp")
    op.drop_column("users", "notify_telegram")
    op.drop_column("users", "notify_email")
