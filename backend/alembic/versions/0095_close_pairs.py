"""T3.12.06 pt.1 — close people are a thing of their own.

`IMPLEMENTATIONPLAN §3.12.3` п. 6: «близкие выносятся из `Connection` в
отдельную сущность со своим механизмом добавления; уровень `close` на строке
контакта снимается». Owner's answers 2026-09-14: asked and accepted; asked only
of a contact; what the pairs already said is carried over —

- both rows `close` → one accepted pair;
- one row `close` → a request from that person, waiting for the other's answer.

Then `connections.tier` is dropped: nothing reads it any more, and a column that
still says «close» next to a table that decides it would be two answers.

Revision ID: 0095
Revises: 0094
Create Date: 2026-09-14
"""
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS close_pairs (
        id UUID PRIMARY KEY,
        requester_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        addressee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        accepted_at TIMESTAMPTZ,
        declined_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        ended_by_id UUID REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_close_pairs_requester_id ON close_pairs (requester_id)",
    "CREATE INDEX IF NOT EXISTS ix_close_pairs_addressee_id ON close_pairs (addressee_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_close_pairs_open
        ON close_pairs (LEAST(requester_id, addressee_id), GREATEST(requester_id, addressee_id))
        WHERE declined_at IS NULL AND ended_at IS NULL
    """,
]

MOVE = [
    # Both said close: one accepted pair, asked by whoever said it first.
    """
    INSERT INTO close_pairs (id, requester_id, addressee_id, requested_at, accepted_at)
    SELECT gen_random_uuid(),
           CASE WHEN a.created_at <= b.created_at THEN a.user_id ELSE b.user_id END,
           CASE WHEN a.created_at <= b.created_at THEN b.user_id ELSE a.user_id END,
           LEAST(a.created_at, b.created_at),
           GREATEST(a.created_at, b.created_at)
    FROM connections a
    JOIN connections b
      ON b.user_id = a.connected_user_id AND b.connected_user_id = a.user_id
    WHERE a.tier = 'close' AND b.tier = 'close' AND a.user_id < b.user_id
    """,
    # One said close: their request, waiting for the other's answer.
    """
    INSERT INTO close_pairs (id, requester_id, addressee_id, requested_at)
    SELECT gen_random_uuid(), a.user_id, a.connected_user_id, a.created_at
    FROM connections a
    LEFT JOIN connections b
      ON b.user_id = a.connected_user_id AND b.connected_user_id = a.user_id
    WHERE a.tier = 'close' AND (b.id IS NULL OR b.tier <> 'close')
    """,
    "ALTER TABLE connections DROP COLUMN tier",
]


def _has_tier(bind) -> bool:
    import sqlalchemy as sa

    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'connections' AND column_name = 'tier'"
            )
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)
    if _has_tier(op.get_bind()):
        for statement in MOVE:
            op.execute(statement)


def downgrade() -> None:
    # Lossy by nature: a declined or ended pair has no tier to go back to.
    op.execute(
        "ALTER TABLE connections ADD COLUMN IF NOT EXISTS tier VARCHAR(16) NOT NULL DEFAULT 'connection'"
    )
    op.execute(
        """
        UPDATE connections c SET tier = 'close'
        FROM close_pairs p
        WHERE p.accepted_at IS NOT NULL AND p.ended_at IS NULL
          AND ((p.requester_id = c.user_id AND p.addressee_id = c.connected_user_id)
            OR (p.addressee_id = c.user_id AND p.requester_id = c.connected_user_id))
        """
    )
    op.execute("DROP TABLE IF EXISTS close_pairs")
