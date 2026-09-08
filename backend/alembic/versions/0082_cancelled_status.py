"""T3.11.27 — a cancelled deal stops being a closed one.

Owner's rule, 2026-09-07: «Отмена до передачи должна подтверждаться обоими
участниками… закроется по таймауту или по времени вылета».

Until now accepting `cancel.requested` set the deal to `closed`, which is the
same word the record uses for a parcel that arrived and was paid for. Two
opposite outcomes under one label: the ledger could not tell a completed deal
from an abandoned one, and neither could a rating built on top of it.

Two enum values, no tables:

- `dealstatus.cancelled` — agreed not to happen. Distinct from `disputed`
  (nobody is claiming anything) and from `closed` (nothing was carried).
- `dealeventtype.cancelled` — its own chain entry, so the hash chain records the
  moment and by whose acceptance.

Revision ID: 0082
Revises: 0081
Create Date: 2026-09-07
"""
from alembic import op


revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction (0006 pattern).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE dealstatus ADD VALUE IF NOT EXISTS 'cancelled'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # Postgres enum values cannot be removed; extra values are harmless.
    pass
