"""receiving_addresses (T_UX.4) — multiple named addresses per user.

Backfills a single "Default" row from the legacy `users.receiving_*`
columns for anyone who filled them. The legacy columns stay for one more
release so we can roll back without data loss; removal is a separate
migration.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-20
"""
from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS receiving_addresses (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label VARCHAR(60) NOT NULL,
            country_iso VARCHAR(2) NOT NULL,
            city VARCHAR(150),
            city_geoname_id INTEGER,
            street VARCHAR(255),
            postal_code VARCHAR(20),
            note VARCHAR(500),
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_receiving_addresses_user_id ON receiving_addresses(user_id)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_receiving_addresses_user_default
        ON receiving_addresses(user_id) WHERE is_default IS TRUE
        """
    )
    # Backfill: one Default row per user with a legacy receiving_country_iso.
    op.execute(
        """
        INSERT INTO receiving_addresses (id, user_id, label, country_iso, city,
            city_geoname_id, street, postal_code, note, is_default, created_at)
        SELECT gen_random_uuid(), id, 'Default', receiving_country_iso,
               receiving_city, receiving_city_geoname_id, receiving_street,
               receiving_postal_code, receiving_note, TRUE, NOW()
          FROM users
         WHERE receiving_country_iso IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS receiving_addresses")
