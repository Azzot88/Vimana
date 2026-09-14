"""T3.12.03 pt.1 — the cargo replaces the order.

Owner's model 2026-09-13 (`D-CARGO-MODEL`): «Груз (Cargo) — то, что везут.
Создаётся перед первой сделкой, ровно один раз, и не меняется»; «заказа как
такового не существует». What used to be an `Order` was half a cargo and half
a deal — the thing carried, and one trip's route, deadline and recipient — and
a cargo that travels through two deals cannot be one row holding one route.

What moves where:

- `orders` → `cargos`, **keeping the id**, so every deal's link is the same UUID
  under a new name and nothing has to be matched up by guessing.
- The cargo's own facts stay on it: category, declared value, currency,
  description. `destination` becomes `final_destination`.
- The shipment number moves from the deal to the cargo. Existing numbers are
  kept as they are — eight letters, no suffix (owner, 2026-09-13).
- Weight, dimensions, fragility and the link are taken from the deal's latest
  agreed terms, which is where they lived. Packaging is not carried over: the
  owner removed it (2026-09-13).
- `final_recipient_id` is the deal's recipient, when it has one.
- The deadline moves to the deal: it is the deadline of one carriage.
- `recipient_contact` goes. The recipient is a person on the platform
  (`T3.12.05`), not a string.
- `deals.position` — where the deal stands in its cargo's chain. Every existing
  cargo has one deal; if a test database holds several deals on one order they
  are numbered by creation, because `(cargo_id, position)` is unique.

Revision ID: 0090
Revises: 0089
Create Date: 2026-09-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


UPGRADE = [
    """
    CREATE TABLE cargos (
        id UUID PRIMARY KEY,
        created_by_id UUID NOT NULL REFERENCES users(id),
        shipment_no VARCHAR(16),
        category VARCHAR(50) NOT NULL,
        declared_value DOUBLE PRECISION NOT NULL,
        currency VARCHAR(4) NOT NULL DEFAULT 'USD',
        description TEXT,
        final_destination VARCHAR(100) NOT NULL,
        final_recipient_id UUID REFERENCES users(id),
        weight_kg DOUBLE PRECISION,
        dimensions_cm JSON,
        fragile BOOLEAN NOT NULL DEFAULT false,
        cargo_url VARCHAR(500),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_cargos_created_by_id ON cargos(created_by_id)",
    "CREATE UNIQUE INDEX ix_cargos_shipment_no ON cargos(shipment_no)",
    """
    INSERT INTO cargos (
        id, created_by_id, shipment_no, category, declared_value, currency,
        description, final_destination, final_recipient_id, weight_kg,
        dimensions_cm, fragile, cargo_url, created_at
    )
    SELECT DISTINCT ON (o.id)
        o.id, o.sender_id, d.shipment_no, o.category, o.declared_value,
        COALESCE(o.currency, 'USD'), o.description, o.destination, d.recipient_id,
        CASE WHEN jsonb_typeof(t.p -> 'weight_kg') = 'number'
             THEN (t.p ->> 'weight_kg')::double precision END,
        CASE WHEN jsonb_typeof(t.p -> 'dimensions_cm') = 'array'
             THEN (t.p -> 'dimensions_cm')::json END,
        CASE WHEN jsonb_typeof(t.p -> 'cargo_fragile') = 'boolean'
             THEN (t.p ->> 'cargo_fragile')::boolean ELSE false END,
        t.p ->> 'cargo_url',
        o.created_at
    FROM orders o
    LEFT JOIN deals d ON d.order_id = o.id
    LEFT JOIN LATERAL (
        SELECT m.card_payload::jsonb AS p
        FROM deal_vault_messages m
        WHERE m.deal_id = d.id
          AND m.card_kind = 'terms.agreed'
          AND m.card_payload IS NOT NULL
        ORDER BY m.created_at DESC
        LIMIT 1
    ) t ON true
    ORDER BY o.id, d.created_at
    """,
    "ALTER TABLE deals ADD COLUMN cargo_id UUID REFERENCES cargos(id)",
    "ALTER TABLE deals ADD COLUMN position INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE deals ADD COLUMN deadline TIMESTAMPTZ",
    """
    UPDATE deals d
    SET cargo_id = d.order_id, deadline = o.deadline, position = r.rn
    FROM orders o,
         (SELECT id, row_number() OVER (PARTITION BY order_id ORDER BY created_at, id) AS rn
          FROM deals) r
    WHERE o.id = d.order_id AND r.id = d.id
    """,
    "ALTER TABLE deals ALTER COLUMN cargo_id SET NOT NULL",
    "CREATE INDEX ix_deals_cargo_id ON deals(cargo_id)",
    "ALTER TABLE deals ADD CONSTRAINT uq_deals_cargo_position UNIQUE (cargo_id, position)",
    "ALTER TABLE deals DROP COLUMN IF EXISTS shipment_no",
    "ALTER TABLE deals DROP COLUMN order_id",
    "DROP TABLE orders",
    "DROP TYPE IF EXISTS orderstatus",
]


def _table_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "orders") or _table_exists(bind, "cargos"):
        return
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Back to orders. Lossy by construction: weight, dimensions, fragility and
    the link lived in the agreed terms before and are still there; a recipient
    contact string never existed for these rows and comes back empty."""
    bind = op.get_bind()
    if not _table_exists(bind, "cargos") or _table_exists(bind, "orders"):
        return
    for statement in (
        "CREATE TYPE orderstatus AS ENUM ('draft','open','matched','closed','cancelled')",
        """
        CREATE TABLE orders (
            id UUID PRIMARY KEY,
            sender_id UUID NOT NULL REFERENCES users(id),
            recipient_contact VARCHAR(255) NOT NULL,
            origin VARCHAR(100) NOT NULL,
            destination VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            declared_value DOUBLE PRECISION NOT NULL,
            currency VARCHAR(4) NOT NULL DEFAULT 'USD',
            description TEXT,
            deadline TIMESTAMPTZ,
            status orderstatus NOT NULL DEFAULT 'matched',
            trip_id UUID REFERENCES trips(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        INSERT INTO orders (
            id, sender_id, recipient_contact, origin, destination, category,
            declared_value, currency, description, deadline, status, trip_id, created_at
        )
        SELECT c.id, c.created_by_id, '', COALESCE(t.origin, ''), c.final_destination,
               c.category, c.declared_value, c.currency, c.description, d.deadline,
               'matched', d.trip_id, c.created_at
        FROM cargos c
        LEFT JOIN deals d ON d.cargo_id = c.id AND d.position = 1
        LEFT JOIN trips t ON t.id = d.trip_id
        """,
        "ALTER TABLE deals ADD COLUMN order_id UUID REFERENCES orders(id)",
        "ALTER TABLE deals ADD COLUMN shipment_no VARCHAR(12)",
        """
        UPDATE deals d SET order_id = d.cargo_id,
               shipment_no = CASE WHEN d.position = 1 THEN c.shipment_no END
        FROM cargos c WHERE c.id = d.cargo_id
        """,
        "ALTER TABLE deals ALTER COLUMN order_id SET NOT NULL",
        "CREATE UNIQUE INDEX ix_deals_shipment_no ON deals(shipment_no)",
        "ALTER TABLE deals DROP CONSTRAINT uq_deals_cargo_position",
        "ALTER TABLE deals DROP COLUMN deadline",
        "ALTER TABLE deals DROP COLUMN position",
        "ALTER TABLE deals DROP COLUMN cargo_id",
        "DROP TABLE cargos",
    ):
        op.execute(statement)
