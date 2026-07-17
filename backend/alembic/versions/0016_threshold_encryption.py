"""Threshold 2-of-3 encryption for DealVault (T2.3)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-17
"""
from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Client-side encryption blob. Legacy T1.21 rows keep is_e2e=false and
    # continue to use text_ciphertext + text_nonce (server-encrypted).
    op.execute(
        "ALTER TABLE deal_vault_messages ADD COLUMN IF NOT EXISTS is_e2e BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE deal_vault_messages ADD COLUMN IF NOT EXISTS wrapped_shares JSONB"
    )
    op.execute(
        "ALTER TABLE deal_vault_messages ADD COLUMN IF NOT EXISTS read_packages JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deal_vault_messages DROP COLUMN IF EXISTS read_packages")
    op.execute("ALTER TABLE deal_vault_messages DROP COLUMN IF EXISTS wrapped_shares")
    op.execute("ALTER TABLE deal_vault_messages DROP COLUMN IF EXISTS is_e2e")
