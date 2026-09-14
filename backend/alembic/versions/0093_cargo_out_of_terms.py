"""T3.12.04 — the cargo leaves the terms.

`D-CARGO-MODEL`: the cargo is written once at the response and does not change,
and the terms of a deal refer to it rather than carrying a copy. Owner's answers
2026-09-14:

- weight lives on the cargo and is required at the response; dimensions are
  optional; the chargeable weight in the terms is computed from them;
- «вскрыть при передаче» is a property of the cargo, given at the response;
- existing cargo is filled from its deal's terms — the latest agreed version,
  or the latest proposal where nothing was agreed. Only empty fields are filled:
  what the response already said stands.

The cargo templates grow the same fields, so a template fills the whole form.

`UPGRADE` is read by `tests/conftest.py` for the test database (columns only);
`BACKFILL` runs here alone — the test database has no history worth moving.

Revision ID: 0093
Revises: 0092
Create Date: 2026-09-14
"""
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TABLE cargos ADD COLUMN IF NOT EXISTS open_on_handover BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cargo_templates ADD COLUMN IF NOT EXISTS weight_kg DOUBLE PRECISION",
    "ALTER TABLE cargo_templates ADD COLUMN IF NOT EXISTS dimensions_cm JSON",
    "ALTER TABLE cargo_templates ADD COLUMN IF NOT EXISTS fragile BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cargo_templates ADD COLUMN IF NOT EXISTS open_on_handover BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cargo_templates ADD COLUMN IF NOT EXISTS cargo_url VARCHAR(500)",
]

BACKFILL = [
    """
    UPDATE cargos c SET
        weight_kg = COALESCE(c.weight_kg, (s.p->>'weight_kg')::double precision),
        dimensions_cm = COALESCE(
            c.dimensions_cm,
            CASE WHEN jsonb_typeof(s.p->'dimensions_cm') = 'array'
                 THEN (s.p->'dimensions_cm')::json END
        ),
        fragile = c.fragile OR COALESCE((s.p->>'cargo_fragile')::boolean, false),
        open_on_handover = c.open_on_handover
            OR COALESCE((s.p->>'cargo_open_on_handover')::boolean, false),
        cargo_url = COALESCE(c.cargo_url, NULLIF(s.p->>'cargo_url', '')),
        description = COALESCE(NULLIF(c.description, ''), NULLIF(s.p->>'cargo_what', ''))
    FROM (
        SELECT DISTINCT ON (d.cargo_id) d.cargo_id, m.card_payload::jsonb AS p
        FROM deal_vault_messages m
        JOIN deals d ON d.id = m.deal_id
        WHERE m.card_kind IN ('terms.agreed', 'terms.proposed', 'terms.countered')
          AND m.card_payload IS NOT NULL
        ORDER BY d.cargo_id, (m.card_kind = 'terms.agreed') DESC, m.created_at DESC
    ) s
    WHERE s.cargo_id = c.id
    """,
]


def upgrade() -> None:
    for statement in UPGRADE + BACKFILL:
        op.execute(statement)


def downgrade() -> None:
    # The backfill is not undone: the terms it was read from are still there.
    op.execute("ALTER TABLE cargo_templates DROP COLUMN IF EXISTS cargo_url")
    op.execute("ALTER TABLE cargo_templates DROP COLUMN IF EXISTS open_on_handover")
    op.execute("ALTER TABLE cargo_templates DROP COLUMN IF EXISTS fragile")
    op.execute("ALTER TABLE cargo_templates DROP COLUMN IF EXISTS dimensions_cm")
    op.execute("ALTER TABLE cargo_templates DROP COLUMN IF EXISTS weight_kg")
    op.execute("ALTER TABLE cargos DROP COLUMN IF EXISTS open_on_handover")
