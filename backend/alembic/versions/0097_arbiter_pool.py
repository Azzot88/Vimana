"""T3.12.09 — the arbiter pool: a dispute is offered, answered, passed on.

`IMPLEMENTATIONPLAN §3.12.6` and the owner's answers 2026-09-14. The standing
offer lives on the dispute (`offered_to_id`, `offered_at`); arbiters who
declined or kept silent are listed in `passed_over` so they are not asked again.

`UPGRADE` is read by `tests/conftest.py` for the test database.

Revision ID: 0097
Revises: 0096
Create Date: 2026-09-15
"""
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TABLE disputes ADD COLUMN IF NOT EXISTS offered_to_id UUID REFERENCES users(id)",
    "ALTER TABLE disputes ADD COLUMN IF NOT EXISTS offered_at TIMESTAMPTZ",
    "ALTER TABLE disputes ADD COLUMN IF NOT EXISTS passed_over JSON NOT NULL DEFAULT '[]'",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE disputes DROP COLUMN IF EXISTS passed_over")
    op.execute("ALTER TABLE disputes DROP COLUMN IF EXISTS offered_at")
    op.execute("ALTER TABLE disputes DROP COLUMN IF EXISTS offered_to_id")
