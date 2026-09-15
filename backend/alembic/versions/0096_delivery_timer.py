"""T3.12.07 pt.2 — silence after the landing goes to the arbiter.

`IMPLEMENTATIONPLAN §3.12.4` п. 6 and the owner's answers 2026-09-14: the sender
is asked once a day whether the parcel arrived; when nobody confirms within the
timer (the sender's own, or the platform's 72 hours) a dispute opens by itself,
opened by the platform rather than by a person.

- `deal_events.actor_id` and `disputes.opened_by` lose NOT NULL: an absent actor
  is «the platform did it», and the chain hash already tells it apart.
- `deals.delivery_reminded_at` — so an hourly sweep asks once a day.
- `users.delivery_timeout_hours` — the sender's own timer; NULL is the default.

`UPGRADE` is read by `tests/conftest.py` for the test database.

Revision ID: 0096
Revises: 0095
Create Date: 2026-09-14
"""
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TABLE deal_events ALTER COLUMN actor_id DROP NOT NULL",
    "ALTER TABLE disputes ALTER COLUMN opened_by DROP NOT NULL",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS delivery_reminded_at TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS delivery_timeout_hours INTEGER",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    # NOT NULL is not restored: platform-opened disputes and their chain entries
    # would violate it, and deleting them would delete evidence.
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS delivery_timeout_hours")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS delivery_reminded_at")
