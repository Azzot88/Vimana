"""Vault completeness: chain event types, deal seal, anchor backend (T3.7)

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-25

No backfill: existing messages/attachments were never chained. The chain stays
valid without them — `GET /deals/{id}/chain` reports coverage honestly instead
of pretending pre-T3.7 content was tamper-evident (same stance as 0025).
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction (0006 pattern).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'message_added'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'file_added'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'sealed'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'identity_ref'")

    op.execute(
        "ALTER TABLE deals ADD COLUMN IF NOT EXISTS sealed_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "ALTER TABLE deal_chain_anchors ADD COLUMN IF NOT EXISTS backend "
        "VARCHAR(16) NOT NULL DEFAULT 'nostr'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deal_chain_anchors DROP COLUMN IF EXISTS backend")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS sealed_at")
    # Postgres enum values cannot be removed; extra values are harmless.
