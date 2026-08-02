"""T3.23 — remember that the identity key changed, and when.

Under `D-KEY-TIERS` every `establish` swaps the account's key: the new one comes
from the browser or an extension, so the npub moves. Everything signed before
that stays signed by a key the account no longer holds — valid, verifiable, and
attached to an identifier that no longer answers.

That is a fact about the account, not a detail of the transition, so it is
stored rather than inferred: the previous public key and the moment it stopped
being current. NULL means the key was never replaced.

The previous *private* key is not stored and never was — this is the public half
only, kept so a person can see "this changed, on this date" instead of noticing
that an old signature no longer matches.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-01
"""
from alembic import op


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS previous_nostr_pubkey VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_changed_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS identity_changed_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS previous_nostr_pubkey")
