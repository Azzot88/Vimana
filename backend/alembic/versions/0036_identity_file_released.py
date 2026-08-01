"""T3.21 — when the key was last handed over for sealing into an Identity Vault.

The rung an account sits on (`D-KEY-TIERS`) is two facts: does the platform
still hold a copy of the key, and does the user hold one. The first is already
in the schema — `nsec_encrypted IS NULL` — and the second cannot be known, only
witnessed: we know we released the key, not that the file was kept.

Hence a timestamp rather than a boolean or a table of "copies". It records the
event we actually observed and leaves the interpretation to one derived string
in the API, so there is no second truth to drift out of step with the first.

NULL means never released. Every existing account starts there, which is
correct: none of them has downloaded anything yet.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-01
"""
from alembic import op


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_file_released_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS identity_file_released_at")
