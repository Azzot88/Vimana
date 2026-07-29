"""T3.14 — passkeys: one identity, several devices.

A credential is a device's key, not the user's identity. Losing a phone drops
one row here; `users.nostr_pubkey` is untouched. That separation is the whole
point of the table — it is why "which device is this" and "who is this" stop
being the same question.

`credential_id` is UNIQUE globally, not per user: WebAuthn credential ids are
what a login ceremony arrives with, and login is usernameless (empty
`allowCredentials`), so the id has to identify an account on its own.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-29
"""
from alembic import op


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webauthn_credentials (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            credential_id BYTEA NOT NULL UNIQUE,
            public_key BYTEA NOT NULL,
            sign_count BIGINT NOT NULL DEFAULT 0,
            transports JSONB,
            aaguid VARCHAR(36),
            device_name VARCHAR(100),
            backed_up BOOLEAN NOT NULL DEFAULT false,
            uv_capable BOOLEAN,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_webauthn_credentials_user_id "
        "ON webauthn_credentials (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webauthn_credentials")
