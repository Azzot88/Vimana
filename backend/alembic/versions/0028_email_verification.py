"""T3.11 — email ownership proof + password_hash nullable.

Two independent things land together because both are prerequisites of the
Phase 3.7 auth model:

1. `password_hash` becomes nullable. Accounts created via Nostr key (T3.13) or
   Passkey (T3.14) have no password at all.
2. Email verification state. The code lives hashed; `attempts` burns a code
   once the cap is hit; `sent_at` drives the resend cooldown.

Backfill: every existing account that has an email is marked verified as of its
creation date. These are live users who registered when no proof was asked —
dropping them into "unverified" would gate them out of creating deals for a
requirement that did not exist when they signed up.

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-26
"""
from alembic import op


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS email_verification_code_hash VARCHAR(255), "
        "ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS email_verification_attempts SMALLINT NOT NULL DEFAULT 0, "
        "ADD COLUMN IF NOT EXISTS email_verification_sent_at TIMESTAMPTZ"
    )
    op.execute(
        "UPDATE users SET email_verified_at = created_at "
        "WHERE email IS NOT NULL AND email_verified_at IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users "
        "DROP COLUMN IF EXISTS email_verified_at, "
        "DROP COLUMN IF EXISTS email_verification_code_hash, "
        "DROP COLUMN IF EXISTS email_verification_expires_at, "
        "DROP COLUMN IF EXISTS email_verification_attempts, "
        "DROP COLUMN IF EXISTS email_verification_sent_at"
    )
    # password_hash NOT NULL is not restored: rows created after this migration
    # may legitimately hold NULL, and the constraint would fail on them.
