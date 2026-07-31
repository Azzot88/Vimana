"""T3.15 — retiring a whole generation of sessions at once.

Changing a password is usually done in a hurry, because someone may be holding
a session they should not. Revoking that session by `jti` is impossible — we
never saw it. So tokens carry `iat`, and this column says how far back is still
acceptable: anything older is refused on the next request.

NULL means nothing was ever retired. Every existing account starts there, so
applying this signs nobody out. Tokens minted before the `iat` claim existed
have no issue time at all; once a user retires their sessions those tokens read
as "older than the cutoff", which is the correct answer for them.

Deliberately not `NOT NULL DEFAULT now()`: that would evict every session on the
platform the moment this migration ran.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-30
"""
from alembic import op


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sessions_valid_from TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS sessions_valid_from")
