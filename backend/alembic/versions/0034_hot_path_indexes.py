"""T_PERF.1 — indexes for the paths every request already walks.

Postgres does not index foreign keys on its own, and nothing here ever asked it
to: before this migration the whole schema carried seven indexes, none of them
on a query the product runs constantly. `core/pagination.py` even documents
"O(log n) via index on (created_at, id)" — an index that did not exist.

Each one below answers a specific query, named in its comment. Composite where
the query filters on one column and orders by another: `(deal_id, created_at,
id)` lets the vault chat be read as one ordered range scan instead of a scan
plus a sort.

Not indexed on purpose:
- `deal_events` — `UNIQUE (deal_id, seq)` already serves lookups by deal.
- `deal_participants`, `trip_inquiries` — their unique constraints start with
  the column that gets filtered, and a leftmost prefix is a usable index.
- `trust_edges.from_user_id` — same reason: it leads
  `uq_trust_edge_pair_kind_source`. Only `to_user_id` (the "verifications
  received" side) had nothing.

Plain `CREATE INDEX`, not `CONCURRENTLY`: the tables hold tens to hundreds of
rows, so each build is instantaneous, and `CONCURRENTLY` cannot run inside the
transaction Alembic wraps a migration in. If these tables ever reach millions of
rows, a future index goes in with `autocommit_block()`.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-01
"""
from alembic import op


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


# (name, DDL body) — `IF NOT EXISTS` so a re-run is a no-op, matching the style
# of the migrations around this one.
_INDEXES = [
    # GET /api/deals — `WHERE sender_id = :me OR carrier_id = :me`. Two separate
    # indexes rather than one composite: the OR is resolved as a bitmap of both.
    ("ix_deals_sender_id", "deals (sender_id)"),
    ("ix_deals_carrier_id", "deals (carrier_id)"),
    # GET /api/trips — `WHERE status = 'open' ORDER BY created_at DESC, id DESC`.
    # Filter and sort in one index; the cursor comparison rides the same order.
    ("ix_trips_status_created", "trips (status, created_at, id)"),
    # Carrier's own trips, and the deletion path that looks up by carrier.
    ("ix_trips_carrier_id", "trips (carrier_id)"),
    # GET /api/deals/{id}/dealvault — the hottest read in the product:
    # `WHERE deal_id = :id ORDER BY created_at, id`.
    (
        "ix_deal_vault_messages_deal_created",
        "deal_vault_messages (deal_id, created_at, id)",
    ),
    # `selectinload(DealVaultMessage.attachments)` issues
    # `WHERE message_id IN (...)` for every page of the chat.
    ("ix_attachments_message_id", "attachments (message_id)"),
    # Inquiry thread, same shape as the vault chat.
    (
        "ix_inquiry_messages_inquiry_created",
        "inquiry_messages (inquiry_id, created_at, id)",
    ),
    # `refresh_trust_counts` counts edges pointing *at* a user.
    ("ix_trust_edges_to_user_id", "trust_edges (to_user_id)"),
    # Verification requests listed per deal (`api/verification.py`).
    ("ix_verification_requests_deal_id", "verification_requests (deal_id)"),
    # Badges read per user on profiles, trip cards and the UBA recompute.
    ("ix_verification_badges_subject_id", "verification_badges (subject_id)"),
]


def upgrade() -> None:
    for name, target in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")


def downgrade() -> None:
    for name, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
