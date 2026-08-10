"""T3.25 — contacts as rows, not as ever more columns on `users`.

A contact was a column: `email`, `phone`, `telegram_chat_id`, `whatsapp_number`,
plus five more holding the state of an email confirmation code. A fifth channel
in that shape means five more columns and a fork of the verification logic.
Phase 3.8 needs four channels and a way to confirm any of them, so the shape
has to change before the channels arrive, not after.

**Partial unique index, not a plain one.** `UNIQUE(channel, value)` over every
row would let an unverified claim on somebody else's number lock the real owner
out forever: nobody checked it, and nobody can now take it. Restricting
uniqueness to confirmed rows makes an unconfirmed claim exactly what it is —
an assertion nobody has tested — while keeping the guarantee that matters: one
confirmed address belongs to one account.

**`users.email` / `users.phone` stay.** Half the codebase reads them, and this
migration is about growing room for channels, not rewriting every reader. They
become the denormalised primary contact; `user_contacts` becomes the truth.

Backfill, and why each choice is the honest one:
- `email` → verified exactly when `email_verified_at` says so.
- `phone` → **unverified**. Nobody has ever confirmed a phone in this system —
  there was no mechanism. Marking them verified would put a claim in the column
  the whole table exists to make trustworthy.
- `telegram_chat_id` / `whatsapp_number` → verified. A chat id only exists
  because someone pressed Start in that chat, and a WhatsApp number was entered
  by the account holder into their own profile.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-09
"""
from alembic import op


revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_contacts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel VARCHAR(16) NOT NULL,
            value VARCHAR(255) NOT NULL,
            verified_at TIMESTAMPTZ NULL,
            is_login BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_contacts_user ON user_contacts (user_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_contacts_verified "
        "ON user_contacts (channel, value) WHERE verified_at IS NOT NULL"
    )
    # Lookup during a code exchange is always (channel, value); the row is
    # found before any user is known, which is the whole point of the table.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_challenges (
            id UUID PRIMARY KEY,
            user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
            channel VARCHAR(16) NOT NULL,
            value VARCHAR(255) NOT NULL,
            code_hash VARCHAR(255) NOT NULL,
            purpose VARCHAR(16) NOT NULL DEFAULT 'verify',
            expires_at TIMESTAMPTZ NOT NULL,
            attempts SMALLINT NOT NULL DEFAULT 0,
            sent_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_verification_challenges_lookup "
        "ON verification_challenges (channel, value)"
    )

    op.execute(
        """
        INSERT INTO user_contacts (id, user_id, channel, value, verified_at, is_login, created_at)
        SELECT gen_random_uuid(), id, 'email', email, email_verified_at, true, created_at
        FROM users
        WHERE email IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_contacts (id, user_id, channel, value, verified_at, is_login, created_at)
        SELECT gen_random_uuid(), id, 'sms', phone, NULL, false, created_at
        FROM users
        WHERE phone IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_contacts (id, user_id, channel, value, verified_at, is_login, created_at)
        SELECT gen_random_uuid(), id, 'telegram', telegram_chat_id, created_at, false, created_at
        FROM users
        WHERE telegram_chat_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_contacts (id, user_id, channel, value, verified_at, is_login, created_at)
        SELECT gen_random_uuid(), id, 'whatsapp', whatsapp_number, created_at, false, created_at
        FROM users
        WHERE whatsapp_number IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS verification_challenges")
    op.execute("DROP TABLE IF EXISTS user_contacts")
