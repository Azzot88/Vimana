"""T_KEYS.1 (слой 4) — contract phase: drop the single-address columns.

T_UX.4 introduced `receiving_addresses` and left `users.receiving_*` in place
for accounts that never migrated (expand → migrate → contract; this is the
contract step). The read fallback was removed 2026-08-02 after a measurement:
one account still carried the old columns and it had a row in the new table
too, so the branch could not fire for anyone.

`downgrade` restores the columns but **not their contents**. That is honest
rather than lazy: the data lives in `receiving_addresses` now, and inventing a
back-fill from it would guess which of several addresses had been the single
one. A downgrade here is a schema rollback, not a time machine.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-02
"""
from alembic import op


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_COLUMNS = (
    "receiving_country_iso",
    "receiving_city",
    "receiving_city_geoname_id",
    "receiving_street",
    "receiving_postal_code",
    "receiving_note",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {column}")


def downgrade() -> None:
    types = {
        "receiving_country_iso": "VARCHAR(2)",
        "receiving_city": "VARCHAR(150)",
        "receiving_city_geoname_id": "INTEGER",
        "receiving_street": "VARCHAR(255)",
        "receiving_postal_code": "VARCHAR(20)",
        "receiving_note": "VARCHAR(500)",
    }
    for column, ddl in types.items():
        op.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {ddl}")
