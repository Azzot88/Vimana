"""Tamper-evident hash chain over deal_events + Nostr anchors (T3.6)

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-24

Backfill note: existing `deal_events` rows are chained in `(timestamp, id)`
order per deal. That ordering is a reconstruction, not a proof — rows written
before this migration were never chained, so the chain attests to history only
from here forward. The backfill exists so the NOT NULL constraint can be added
and future entries link onto something; it does not retroactively make old rows
tamper-evident.

The hash is computed by importing `app.core.deal_chain.compute_entry_hash`
rather than reimplementing it here, deliberately: one definition of the preimage,
so a change to it breaks loudly everywhere instead of silently diverging between
the backfill and runtime verification.
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

from app.core.deal_chain import compute_entry_hash

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _backfill_chain(conn) -> None:
    rows = conn.execute(
        sa.text(
            "SELECT id::text AS id, deal_id::text AS deal_id, "
            "event_type::text AS event_type, actor_id::text AS actor_id, "
            "nostr_event_id, payload::text AS payload, timestamp "
            "FROM deal_events ORDER BY deal_id, timestamp, id"
        )
    ).fetchall()

    seq_by_deal: dict[str, int] = {}
    prev_by_deal: dict[str, bytes | None] = {}

    for row in rows:
        deal_key = row.deal_id
        seq = seq_by_deal.get(deal_key, 0) + 1
        seq_by_deal[deal_key] = seq
        prev_hash = prev_by_deal.get(deal_key)

        entry_hash = compute_entry_hash(
            deal_id=uuid.UUID(deal_key),
            seq=seq,
            timestamp=row.timestamp,
            event_type=row.event_type,
            actor_id=uuid.UUID(row.actor_id) if row.actor_id else None,
            nostr_event_id=row.nostr_event_id,
            payload=json.loads(row.payload) if row.payload is not None else None,
            prev_hash=prev_hash,
        )

        # Two separate statements — asyncpg can't infer parameter type when
        # a param sits inside a CASE whose branches produce different types
        # (both need to know the target type at plan time, and NULL is
        # untyped). Splitting sidesteps `AmbiguousParameterError`.
        if prev_hash is None:
            conn.execute(
                sa.text(
                    "UPDATE deal_events SET seq = :seq, "
                    "entry_hash = decode(:entry_hash, 'hex'), "
                    "prev_hash = NULL "
                    "WHERE id = :id"
                ),
                {"seq": seq, "entry_hash": entry_hash.hex(), "id": row.id},
            )
        else:
            conn.execute(
                sa.text(
                    "UPDATE deal_events SET seq = :seq, "
                    "entry_hash = decode(:entry_hash, 'hex'), "
                    "prev_hash = decode(:prev_hash, 'hex') "
                    "WHERE id = :id"
                ),
                {
                    "seq": seq,
                    "entry_hash": entry_hash.hex(),
                    "prev_hash": prev_hash.hex(),
                    "id": row.id,
                },
            )
        prev_by_deal[deal_key] = entry_hash


def upgrade() -> None:
    conn = op.get_bind()

    # Nullable first so existing rows survive the ALTER; tightened after backfill.
    op.execute("ALTER TABLE deal_events ADD COLUMN IF NOT EXISTS seq BIGINT")
    op.execute("ALTER TABLE deal_events ADD COLUMN IF NOT EXISTS entry_hash BYTEA")
    op.execute("ALTER TABLE deal_events ADD COLUMN IF NOT EXISTS prev_hash BYTEA")

    _backfill_chain(conn)

    op.execute("ALTER TABLE deal_events ALTER COLUMN seq SET NOT NULL")
    op.execute("ALTER TABLE deal_events ALTER COLUMN entry_hash SET NOT NULL")
    op.execute(
        "ALTER TABLE deal_events ADD CONSTRAINT uq_deal_events_deal_seq "
        "UNIQUE (deal_id, seq)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_chain_anchors (
            id UUID PRIMARY KEY,
            deal_id UUID NOT NULL REFERENCES deals(id),
            seq BIGINT NOT NULL,
            entry_hash BYTEA NOT NULL,
            nostr_event_id VARCHAR(64) NOT NULL,
            nostr_pubkey VARCHAR(64) NOT NULL,
            relays JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_deal_chain_anchors_deal_seq UNIQUE (deal_id, seq)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_chain_anchors_deal_id "
        "ON deal_chain_anchors (deal_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_chain_anchors")
    op.execute(
        "ALTER TABLE deal_events DROP CONSTRAINT IF EXISTS uq_deal_events_deal_seq"
    )
    op.execute("ALTER TABLE deal_events DROP COLUMN IF EXISTS prev_hash")
    op.execute("ALTER TABLE deal_events DROP COLUMN IF EXISTS entry_hash")
    op.execute("ALTER TABLE deal_events DROP COLUMN IF EXISTS seq")
