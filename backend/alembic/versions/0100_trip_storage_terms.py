"""T_DEAL.1 — storage terms on the trip.

The carrier says two numbers when they publish: how many days of storage are
free and what a day costs after that. Both live in one JSON column because they
are one answer — a price without a free period, or a free period without a
price, is half a tariff and could not be shown to a sender as terms.

NULL means «this carrier does not store, or did not say», which is deliberately
not the same as free storage (`core.deal_storage.terms_of` refuses to complete a
half-written tariff).

`UPGRADE` is read by `tests/conftest.py` for the test database, which is never
reset and whose tables `create_all` builds but never alters. A statement list —
not `op.add_column` — for exactly that reason, and a literal one because the
conftest reads it with `ast.literal_eval` rather than importing this file.

Revision ID: 0100
Revises: 0099
Create Date: 2026-09-20
"""
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TABLE trips ADD COLUMN IF NOT EXISTS storage_terms JSON",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS storage_terms")
