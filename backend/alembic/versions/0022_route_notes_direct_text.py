"""route_notes + platform_notices — direct text (T_UX.2 pt.4)

Replaces i18n_key columns with direct headline/body text. Backfills
existing rows from the old keys (usually human-readable when written).
Adds the same fields to platform_notices (previously key-only).

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-19
"""
from alembic import op


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE route_notes ADD COLUMN IF NOT EXISTS headline VARCHAR(500) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE route_notes ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT ''")
    op.execute("UPDATE route_notes SET headline = headline_i18n_key WHERE headline = ''")
    op.execute("UPDATE route_notes SET body = body_i18n_key WHERE body = ''")
    op.execute("ALTER TABLE route_notes DROP COLUMN IF EXISTS headline_i18n_key")
    op.execute("ALTER TABLE route_notes DROP COLUMN IF EXISTS body_i18n_key")

    op.execute("ALTER TABLE platform_notices ADD COLUMN IF NOT EXISTS headline VARCHAR(500) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE platform_notices ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT ''")
    op.execute("UPDATE platform_notices SET headline = key WHERE headline = ''")


def downgrade() -> None:
    op.execute("ALTER TABLE route_notes ADD COLUMN IF NOT EXISTS headline_i18n_key VARCHAR(100) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE route_notes ADD COLUMN IF NOT EXISTS body_i18n_key VARCHAR(100) NOT NULL DEFAULT ''")
    op.execute("UPDATE route_notes SET headline_i18n_key = headline WHERE headline_i18n_key = ''")
    op.execute("UPDATE route_notes SET body_i18n_key = body WHERE body_i18n_key = ''")
    op.execute("ALTER TABLE route_notes DROP COLUMN IF EXISTS headline")
    op.execute("ALTER TABLE route_notes DROP COLUMN IF EXISTS body")

    op.execute("ALTER TABLE platform_notices DROP COLUMN IF EXISTS headline")
    op.execute("ALTER TABLE platform_notices DROP COLUMN IF EXISTS body")
