"""Nostr keypair per user (T2.2)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-14

Adds custodial nsec storage (AES-256-GCM), self-custody flag, and backfills
keypairs for existing users. Idempotent — safe to re-run after partial failure.

The keypair backfill uses the running Python process to generate secp256k1
keys (`coincurve`) and encrypt them (`app.core.crypto`), so the migration
requires `NSEC_ENCRYPTION_KEY` in env when there are legacy users.
"""
import os
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nsec_encrypted BYTEA")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nsec_nonce BYTEA")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS key_self_custody BOOLEAN "
        "NOT NULL DEFAULT false"
    )

    # Backfill: legacy users without nostr_pubkey get a fresh custodial keypair.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE nostr_pubkey IS NULL OR nsec_encrypted IS NULL"
        )
    ).fetchall()
    if not rows:
        return

    from app.core.keypair import encrypt_nsec, generate_keypair

    if not os.getenv("NSEC_ENCRYPTION_KEY", "").strip():
        # If key isn't set we skip backfill — new users will still get keypairs
        # via app.api.auth.register, and legacy users can be backfilled later
        # via `scripts/backfill_keypairs.py`.
        return

    for (user_id,) in rows:
        nsec_hex, npub_hex = generate_keypair()
        nonce, ct = encrypt_nsec(nsec_hex)
        bind.execute(
            sa.text(
                "UPDATE users SET nostr_pubkey = :npub, "
                "nsec_encrypted = :ct, nsec_nonce = :n "
                "WHERE id = :id"
            ),
            {"npub": npub_hex, "ct": ct, "n": nonce, "id": user_id},
        )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS key_self_custody")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS nsec_nonce")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS nsec_encrypted")
