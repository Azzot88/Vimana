"""User Zero + arbiter role + disputes

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-07

Notes on idempotency:
- Every DDL step guards for prior partial application so the migration can be
  re-run after a mid-flight failure without manual DB cleanup.
- `sa.Enum(create_type=False)` is intentionally NOT used — `sa.Enum` does not
  propagate `create_type` to `postgresql.ENUM`, and `op.create_table` will
  still dispatch `_on_table_create` on the enum type. We build the `disputes`
  table with raw SQL that references `disputestatus` by name.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Boolean flags on users — idempotent.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN "
        "NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_arbiter BOOLEAN "
        "NOT NULL DEFAULT false"
    )

    # 2) Extend DealEventType enum. ALTER TYPE ... ADD VALUE cannot run inside
    # a transaction, hence the autocommit block. `IF NOT EXISTS` handles retries.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'dispute_opened'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'arbiter_opened'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'dispute_resolved'")

    # 3) DisputeStatus enum — guard by pg_type existence check.
    has_type = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'disputestatus'")
    ).fetchone()
    if not has_type:
        op.execute("CREATE TYPE disputestatus AS ENUM ('open', 'claimed', 'resolved')")

    # 4) disputes table — raw SQL to avoid SQLAlchemy's `_on_table_create`
    # trying to re-create the enum type.
    has_table = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'disputes'"
        )
    ).fetchone()
    if not has_table:
        op.execute(
            """
            CREATE TABLE disputes (
                id UUID PRIMARY KEY,
                deal_id UUID NOT NULL REFERENCES deals(id),
                opened_by UUID NOT NULL REFERENCES users(id),
                arbiter_id UUID REFERENCES users(id),
                reason TEXT NOT NULL,
                status disputestatus NOT NULL DEFAULT 'open',
                verdict TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ,
                CONSTRAINT uq_disputes_deal_id UNIQUE (deal_id)
            )
            """
        )

    # 5) Promote User Zero (idempotent — no-op if user missing or already superuser).
    op.execute(
        "UPDATE users SET is_superuser = true "
        "WHERE email = 'nyxter@dealvault.club' AND is_superuser = false"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS disputes")
    op.execute("DROP TYPE IF EXISTS disputestatus")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_arbiter")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_superuser")
