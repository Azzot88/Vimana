"""T_UX.29 pt.7 — the notification feed and the push seam.

Two tables, and neither belongs to the deal chain: a notification is a courtesy,
not evidence. What happened is the card in the vault; this is only the record of
who has not seen it yet, and deleting a row here changes nothing about the deal.

`notifications` is addressed per person on purpose — a deal has three people in
it and each needs their own `read_at`. The partial index is the one the bell
asks for on every beat («сколько непрочитано»), and it is partial because the
answer is almost always a handful of rows out of a growing table.

`push_subscriptions` is collected and not yet sent to: the rows can accumulate
from the day the button exists, so switching delivery on later is a worker task
and a pair of VAPID keys, not a migration plus a consent flow nobody has given.

`UPGRADE` is read by `tests/conftest.py` for the test database, which is never
reset and whose tables `create_all` builds but never alters. A literal statement
list for exactly that reason — the conftest reads it with `ast.literal_eval`
rather than importing this file.

Revision ID: 0102
Revises: 0101
Create Date: 2026-09-20
"""
from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind VARCHAR(40) NOT NULL,
        deal_id UUID REFERENCES deals(id) ON DELETE CASCADE,
        trip_id UUID REFERENCES trips(id) ON DELETE CASCADE,
        payload JSON,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        read_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_created"
    " ON notifications (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_unread"
    " ON notifications (user_id) WHERE read_at IS NULL",
    """
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        endpoint VARCHAR(500) NOT NULL,
        p256dh VARCHAR(200) NOT NULL,
        auth VARCHAR(100) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_push_subscription_endpoint UNIQUE (endpoint)
    )
    """,
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
    op.execute("DROP TABLE IF EXISTS notifications")
