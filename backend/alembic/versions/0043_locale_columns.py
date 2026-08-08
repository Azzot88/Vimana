"""T_UX.9 — remember which language to write to a person in.

Every letter the platform sends was Russian, while the interface speaks six
languages. Nothing recorded a preference, so there was nothing to render
against — the gap was in the schema, not in the templates.

`users.locale` defaults to `en` rather than `ru`. The default applies to rows
that predate this column and to any path that forgets to pass a language, and
in both cases English is the safer guess for a product launching on the
UAE ↔ US corridor. Existing accounts are not backfilled to Russian: guessing a
language from a name is exactly the kind of inference that gets it wrong.

`waitlist.locale` is nullable. A row from before this migration genuinely has
no known language, and NULL says that, where `'en'` would claim we asked.
Rendering falls back to English either way, but only one of the two is honest
about why.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-08
"""
from alembic import op


revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "locale VARCHAR(5) NOT NULL DEFAULT 'en'"
    )
    op.execute("ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS locale VARCHAR(5)")


def downgrade() -> None:
    op.execute("ALTER TABLE waitlist DROP COLUMN IF EXISTS locale")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locale")
