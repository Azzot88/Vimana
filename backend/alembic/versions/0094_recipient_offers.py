"""T3.12.05 pt.1 — the recipient is offered the role, and answers.

`D-CARGO-MODEL` (4), `IMPLEMENTATIONPLAN §3.12.3`: rights do not arrive before
the answer. A `deal_participants` row was either an invite or a recipient; it is
now an offer with four states, and `declined_at` is the one that had no column.

`users.refuses_recipient_offers` — «отказавшийся может запретить назначать себя
получателем»: an account setting, enforced by the API rather than by a hidden
button.

`UPGRADE` is read by `tests/conftest.py` for the test database.

Revision ID: 0094
Revises: 0093
Create Date: 2026-09-14
"""
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TABLE deal_participants ADD COLUMN IF NOT EXISTS declined_at TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS refuses_recipient_offers BOOLEAN NOT NULL DEFAULT false",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS refuses_recipient_offers")
    op.execute("ALTER TABLE deal_participants DROP COLUMN IF EXISTS declined_at")
