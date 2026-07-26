"""T3.12 pt.1 — identity schema: npub uniqueness, key loss, publish attribution.

Three things, all prerequisites of the Phase 3.7 identity model:

1. `users.nostr_pubkey` gets a UNIQUE constraint. It had none — two accounts
   could claim the same npub, which makes "the key is the identity" meaningless
   and would make key-based login ambiguous. Left **nullable** on purpose: the
   NOT NULL half waits until `ensure_service_keys` (runs on startup) has
   backfilled every account, so the constraint cannot fail mid-deploy.

2. `users.key_lost_at` — terminal state for an account whose identity key is
   gone. Losing the key is not the same as losing access: a user with a live
   passkey still signs in but can no longer sign or read their own encrypted
   history, and a counterparty must be able to see that.

3. `trips.nostr_published_by_pubkey` — which key published a trip event. NIP-09
   requires a deletion to be signed by the *same* key that published; without
   this column, a trip published under the platform key could not be retracted
   once the carrier moved to their own key.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-26
"""
from alembic import op


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS key_lost_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE trips "
        "ADD COLUMN IF NOT EXISTS nostr_published_by_pubkey VARCHAR(64)"
    )
    # Backfill attribution for anything already published: before this phase the
    # only signer was the carrier's own (service) key.
    op.execute(
        "UPDATE trips t SET nostr_published_by_pubkey = u.nostr_pubkey "
        "FROM users u "
        "WHERE t.carrier_id = u.id "
        "AND t.nostr_event_id IS NOT NULL "
        "AND t.nostr_published_by_pubkey IS NULL"
    )
    # Guarded: re-running on a database that already has the constraint (or a
    # partially applied deploy) must not abort the upgrade.
    op.execute(
        "DO $$ BEGIN "
        "ALTER TABLE users ADD CONSTRAINT uq_users_nostr_pubkey "
        "UNIQUE (nostr_pubkey); "
        "EXCEPTION WHEN duplicate_table THEN NULL; "
        "WHEN duplicate_object THEN NULL; "
        "END $$;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_nostr_pubkey")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS key_lost_at")
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS nostr_published_by_pubkey")
