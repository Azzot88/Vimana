"""Receiving address in User profile (T1.26)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14

Adds 6 nullable fields for user's receiving address. Private by design:
never exposed in list-endpoints or public UserOut. Idempotent.
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col, ddl in (
        ("receiving_country_iso", "VARCHAR(2)"),
        ("receiving_city", "VARCHAR(150)"),
        ("receiving_city_geoname_id", "INTEGER"),
        ("receiving_street", "VARCHAR(255)"),
        ("receiving_postal_code", "VARCHAR(20)"),
        ("receiving_note", "VARCHAR(500)"),
    ):
        op.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}")


def downgrade() -> None:
    for col in (
        "receiving_note",
        "receiving_postal_code",
        "receiving_street",
        "receiving_city_geoname_id",
        "receiving_city",
        "receiving_country_iso",
    ):
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {col}")
