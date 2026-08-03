"""T3.8 — scan state per attachment, so an unscanned file is a known unknown.

Owner's decision 2026-08-02 replaced fail-closed with fail-open plus a queue: a
scanner outage must not stop people uploading, but it must not silently pass
either. That only works if every file carries what we actually know about it.

`pending` is the default for existing rows, and that is the honest value — none
of them were ever scanned. The consequence is intended: switching a scanner on
for the first time gives the rescan task the whole backlog, which is exactly
what "after activation they must be checked" asks for.

Three states, no fourth. There is deliberately no `skipped` for "scanning was
off": from the reader's side that is the same situation as "the scanner was
down" — the file is not known to be clean — and a second word for it would
invite treating one of them as safe.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-02
"""
from alembic import op


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS "
        "scan_status VARCHAR(10) NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS scanned_at TIMESTAMPTZ"
    )
    # The rescan task reads exactly this predicate every tick, and the counter
    # on the admin page reads it on every load.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_attachments_scan_status "
        "ON attachments (scan_status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_attachments_scan_status")
    op.execute("ALTER TABLE attachments DROP COLUMN IF EXISTS scanned_at")
    op.execute("ALTER TABLE attachments DROP COLUMN IF EXISTS scan_status")
