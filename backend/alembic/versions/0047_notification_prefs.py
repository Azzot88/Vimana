"""T3.32 — event class × channel, in one JSONB column.

The three booleans stay. They stop steering delivery, but the screen still reads
them to say whether a channel is connected at all, and dropping a column that
half the codebase touches is a separate piece of work from adding a matrix.

**The backfill is the point of this migration.** Writing `{}` for everybody and
letting the defaults apply would be a migration that silently turns notifications
back **on** for every account that had switched them off — the one outcome a
preferences migration must never produce. So each existing choice is written out
per class instead: whoever had email off keeps it off, for every class that can
be switched.

`security` is not written: it cannot be switched off, `wants` never consults
storage for it, and a stored row for it would be a value that looks like a
setting and does nothing. The three classes with no producer yet (`vault`,
`trust`, `dispute`) are not written either — nobody has expressed a preference
about a message that has never arrived, and the default is what they should get
when it does.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-11
"""
from alembic import op


revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "notification_prefs JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    # One statement, built from the three booleans. `jsonb_build_object` rather
    # than string concatenation: a display name is not involved, but the habit of
    # assembling JSON by hand in SQL is how a stray quote becomes a failed
    # migration on a table nobody can afford to have half-written.
    op.execute(
        """
        UPDATE users SET notification_prefs = jsonb_build_object(
            'deal', jsonb_build_object(
                'email', notify_email,
                'telegram', notify_telegram,
                'whatsapp', notify_whatsapp
            ),
            'deadline', jsonb_build_object(
                'email', notify_email,
                'telegram', notify_telegram,
                'whatsapp', notify_whatsapp
            )
        )
        WHERE notification_prefs = '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS notification_prefs")
