"""T3.16 — recovery codes: a spare way in, never a spare identity.

Ten codes per account, stored as SHA-256 digests. Not bcrypt: a code is twelve
characters from a 31-symbol alphabet chosen by `secrets` — about 59 bits, with
no dictionary to survive — and a fast digest is what lets an attempt be looked
up by equality instead of verified against every unused code in turn. The
reasoning lives in `core/security.hash_recovery_code`.

`used_at` rather than deleting the row: "this code was spent, and when" is the
kind of thing a person asks after an unexpected sign-in, and a missing row
cannot answer it.

ON DELETE CASCADE because these are worth nothing without their account.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-01
"""
from alembic import op


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery_codes (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash VARCHAR(255) NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_recovery_codes_user_id ON recovery_codes (user_id)"
    )
    # Lookup is always (this account, this digest, unused) — the index the
    # consume path actually walks.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_recovery_codes_user_hash "
        "ON recovery_codes (user_id, code_hash)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recovery_codes")
