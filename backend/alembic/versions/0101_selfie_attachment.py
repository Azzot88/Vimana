"""T_UX.28 п.4 — a selfie is its own kind of evidence.

Owner, 2026-09-19: «селфи с отправителем, фото передачи, фото отправки на почте
и др.» A selfie answers a different question from a photograph of the parcel —
who was standing there, rather than what changed hands — and an arbiter reads
these labels. Filing one as `handoff_photo` would lose the only tie between a
face and a meeting the record has.

`UPGRADE` is read by `tests/conftest.py` for the test database. Enum values can
only be added, never removed, so `downgrade` does nothing: dropping a value
would need the type rebuilt and every row rewritten, and a value nobody writes
costs nothing where it stands.

Revision ID: 0101
Revises: 0100
Create Date: 2026-09-20
"""
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TYPE attachmentkind ADD VALUE IF NOT EXISTS 'selfie'",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Nothing: a Postgres enum value cannot be dropped in place, and one that
    nothing writes is harmless where it is."""
