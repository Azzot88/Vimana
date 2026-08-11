"""T3.27 — room for an exchange that starts before the code exists.

Telegram runs backwards from every other channel. A bot cannot write to somebody
who has never written to it, so a sign-in through it begins with a link, and the
code is minted only when the person presses Start. Two consequences, one column
each:

- **`code_hash` becomes nullable.** The row has to exist from the moment the
  link is issued — otherwise the webhook cannot tell a nonce we minted from a
  string a stranger typed — but there is no code in it yet. Storing a hash of
  something that was never sent would put a value in the column that looks like
  a code and is not; null says exactly what is true.
- **`resolved_value` is added.** The chat id is learned at `/start` and needed
  again at `otp/verify` to decide whose account this is. Every other channel
  leaves it null: there the caller names the target up front.
- **`resolved_label` too.** An account born from an address gets the local part
  as a provisional name; a chat id has no such part, and the welcome screen is
  skippable by design — so without the name Telegram already knows, such an
  account could reach a counterparty blank.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-11
"""
from alembic import op


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE verification_challenges ALTER COLUMN code_hash DROP NOT NULL")
    op.execute(
        "ALTER TABLE verification_challenges ADD COLUMN IF NOT EXISTS "
        "resolved_value VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE verification_challenges ADD COLUMN IF NOT EXISTS "
        "resolved_label VARCHAR(100)"
    )


def downgrade() -> None:
    # Rows opened but never minted have no code and cannot get one retroactively;
    # they are dropped rather than filled with a placeholder that would verify
    # against nothing.
    op.execute("DELETE FROM verification_challenges WHERE code_hash IS NULL")
    op.execute("ALTER TABLE verification_challenges DROP COLUMN IF EXISTS resolved_label")
    op.execute("ALTER TABLE verification_challenges DROP COLUMN IF EXISTS resolved_value")
    op.execute("ALTER TABLE verification_challenges ALTER COLUMN code_hash SET NOT NULL")
