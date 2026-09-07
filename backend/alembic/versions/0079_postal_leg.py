"""T3.11.17 — the onward postal leg becomes a state the record knows.

**44.9 % of carriers on this market post the parcel onward** inside the
destination country. For half the deals there is therefore a leg between «in the
carrier's hands» and «in the recipient's» — and `DealStatus` / `DealEventType`
knew `handoff` and `received` and nothing between them. That gap is exactly what
made an arbiter's question unanswerable: when a parcel goes missing, the record
could not say which leg lost it.

Three enum values, no tables:

- `dealstatus.posted` — handed to a postal service, not yet received. Calling it
  `delivered` would be the platform asserting something neither party said.
- `dealeventtype.posted` — its own chain entry, for the same reason.
- `attachmentkind.pre_seal_photo` — the parcel photographed **before it was
  sealed** (`USERJOURNEY` Этап 4a). Not `handoff_photo` reused: an arbiter reads
  these labels, and «фото передачи» over a picture of an open box would
  misdescribe the only evidence this leg has.

Revision ID: 0079
Revises: 0078
Create Date: 2026-09-07
"""
from alembic import op


revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction (0006 pattern).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE dealstatus ADD VALUE IF NOT EXISTS 'posted'")
        op.execute("ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'posted'")
        op.execute(
            "ALTER TYPE attachmentkind ADD VALUE IF NOT EXISTS 'pre_seal_photo'"
        )


def downgrade() -> None:
    # Postgres enum values cannot be removed; extra values are harmless.
    pass
