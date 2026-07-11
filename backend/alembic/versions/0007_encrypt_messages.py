"""At-rest encryption for DealVault messages (T1.21)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-11

Adds `text_ciphertext` + `text_nonce` (BYTEA) columns, backfills existing
plaintext through AES-256-GCM using `MESSAGE_ENCRYPTION_KEY`, then drops the
`text` column. Idempotent — safe to re-run after partial failure.
"""
import base64
import os

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _load_key() -> bytes:
    raw = os.getenv("MESSAGE_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise RuntimeError(
            "MESSAGE_ENCRYPTION_KEY is required to run migration 0007. "
            "Generate with `openssl rand -base64 32`."
        )
    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise RuntimeError("MESSAGE_ENCRYPTION_KEY must decode to 32 bytes")
    return key


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Add new columns (nullable — legacy rows still hold plaintext until backfill).
    op.execute(
        "ALTER TABLE deal_vault_messages ADD COLUMN IF NOT EXISTS text_ciphertext BYTEA"
    )
    op.execute(
        "ALTER TABLE deal_vault_messages ADD COLUMN IF NOT EXISTS text_nonce BYTEA"
    )

    # 2) Backfill: encrypt existing plaintext rows that haven't been migrated yet.
    has_text = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'deal_vault_messages' AND column_name = 'text'"
        )
    ).fetchone()

    if has_text:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = _load_key()
        aes = AESGCM(key)
        result = bind.execute(
            sa.text(
                "SELECT id, text FROM deal_vault_messages "
                "WHERE text IS NOT NULL AND text_ciphertext IS NULL"
            )
        )
        for row in result.fetchall():
            nonce = os.urandom(12)
            ct = aes.encrypt(nonce, row.text.encode("utf-8"), None)
            bind.execute(
                sa.text(
                    "UPDATE deal_vault_messages "
                    "SET text_ciphertext = :ct, text_nonce = :n WHERE id = :id"
                ),
                {"ct": ct, "n": nonce, "id": row.id},
            )

        # 3) Drop plaintext column now that everything is encrypted.
        op.execute("ALTER TABLE deal_vault_messages DROP COLUMN text")


def downgrade() -> None:
    # Best-effort: restore `text` column empty. Existing rows can't be decrypted
    # here (would need Python + key), so downgrade is lossy by design.
    op.execute("ALTER TABLE deal_vault_messages ADD COLUMN IF NOT EXISTS text TEXT")
    op.execute("ALTER TABLE deal_vault_messages DROP COLUMN IF EXISTS text_ciphertext")
    op.execute("ALTER TABLE deal_vault_messages DROP COLUMN IF EXISTS text_nonce")
