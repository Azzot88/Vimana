"""NIP-01 event fields on vault messages + deal events (T2.2 pt.2)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-17
"""
from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


_TABLES = ("deal_vault_messages", "deal_events")


def upgrade() -> None:
    for tbl in _TABLES:
        op.execute(
            f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS nostr_event_id VARCHAR(64)"
        )
        op.execute(
            f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS nostr_created_at BIGINT"
        )
        op.execute(
            f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS nostr_pubkey VARCHAR(64)"
        )


def downgrade() -> None:
    for tbl in _TABLES:
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN IF EXISTS nostr_pubkey")
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN IF EXISTS nostr_created_at")
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN IF EXISTS nostr_event_id")
