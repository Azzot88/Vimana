"""Repair the one field `0093` failed to move: the cargo's dimensions.

`0093` carried the cargo out of the terms. Every field arrived except the size:
the branch cast `jsonb → json` directly, which yields nothing here, so a cargo
migrated from an old deal kept `dimensions_cm = NULL` while its terms card still
held `[30, 20, 10]`. Found 2026-09-15, when the data move finally got a test of
its own (`tests/test_migrations.py`).

`0093` is corrected for databases created later; this repairs the ones that
already ran it. Idempotent and non-destructive: `COALESCE` leaves a cargo that
already has a size alone.

Revision ID: 0098
Revises: 0097
Create Date: 2026-09-15
"""
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None


BACKFILL = [
    """
    UPDATE cargos c SET
        dimensions_cm = COALESCE(c.dimensions_cm, (s.p->>'dimensions_cm')::json)
    FROM (
        SELECT DISTINCT ON (d.cargo_id) d.cargo_id, m.card_payload::jsonb AS p
        FROM deal_vault_messages m
        JOIN deals d ON d.id = m.deal_id
        WHERE m.card_kind IN ('terms.agreed', 'terms.proposed', 'terms.countered')
          AND m.card_payload IS NOT NULL
        ORDER BY d.cargo_id, (m.card_kind = 'terms.agreed') DESC, m.created_at DESC
    ) s
    WHERE s.cargo_id = c.id
      AND c.dimensions_cm IS NULL
      AND jsonb_typeof(s.p->'dimensions_cm') = 'array'
    """,
]


def upgrade() -> None:
    for statement in BACKFILL:
        op.execute(statement)


def downgrade() -> None:
    # Nothing to undo: this only fills in what `0093` was meant to fill in, and
    # a size put back to NULL would be the defect, not the state before it.
    pass
