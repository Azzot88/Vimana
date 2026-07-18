"""Trip Nostr publish fields (T3.5)

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-18
"""
from alembic import op


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE trips ADD COLUMN IF NOT EXISTS nostr_event_id VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE trips ADD COLUMN IF NOT EXISTS nostr_published_at TIMESTAMPTZ"
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_trips_nostr_event_id'
            ) THEN
                ALTER TABLE trips
                ADD CONSTRAINT uq_trips_nostr_event_id UNIQUE (nostr_event_id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE trips DROP CONSTRAINT IF EXISTS uq_trips_nostr_event_id")
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS nostr_published_at")
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS nostr_event_id")
