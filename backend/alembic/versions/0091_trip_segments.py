"""T3.12.03 pt.3 — a trip's flights are segments, not legs.

`D-CARGO-MODEL` (owner, 2026-09-13): «слова "нога", "хоп" и "лег" из PRD и кода
убираем совсем». On this platform a *deal* is one carriage of a cargo, and the
word «leg» had come to mean that as well as a flight of a trip — the same word
for two things is how the first draft of the model went wrong. The flight is a
**segment of a trip** (`TripSegment`); nothing else is called a leg.

Renamed, not recreated: the rows, the unique constraint, the three checks and
the index keep what they hold, and a check expression follows its column's new
name on its own. Guarded so a database that already went through the rename —
or a test database fixed by `conftest` — is left alone.

Revision ID: 0091
Revises: 0090
Create Date: 2026-09-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


UPGRADE = [
    "ALTER TABLE trip_legs RENAME TO trip_segments",
    "ALTER TABLE trip_segments RENAME COLUMN leg_order TO segment_order",
    "ALTER TABLE trip_segments RENAME CONSTRAINT uq_trip_legs_order TO uq_trip_segments_order",
    "ALTER TABLE trip_segments RENAME CONSTRAINT ck_trip_legs_order_nonneg TO ck_trip_segments_order_nonneg",
    "ALTER TABLE trip_segments RENAME CONSTRAINT ck_trip_legs_distinct TO ck_trip_segments_distinct",
    "ALTER TABLE trip_segments RENAME CONSTRAINT ck_trip_legs_flown_by TO ck_trip_segments_flown_by",
    "ALTER INDEX IF EXISTS ix_trip_legs_trip_order RENAME TO ix_trip_segments_trip_order",
]

DOWNGRADE = [
    "ALTER INDEX IF EXISTS ix_trip_segments_trip_order RENAME TO ix_trip_legs_trip_order",
    "ALTER TABLE trip_segments RENAME CONSTRAINT ck_trip_segments_flown_by TO ck_trip_legs_flown_by",
    "ALTER TABLE trip_segments RENAME CONSTRAINT ck_trip_segments_distinct TO ck_trip_legs_distinct",
    "ALTER TABLE trip_segments RENAME CONSTRAINT ck_trip_segments_order_nonneg TO ck_trip_legs_order_nonneg",
    "ALTER TABLE trip_segments RENAME CONSTRAINT uq_trip_segments_order TO uq_trip_legs_order",
    "ALTER TABLE trip_segments RENAME COLUMN segment_order TO leg_order",
    "ALTER TABLE trip_segments RENAME TO trip_legs",
]


def _table_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "trip_legs") or _table_exists(bind, "trip_segments"):
        return
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "trip_segments") or _table_exists(bind, "trip_legs"):
        return
    for statement in DOWNGRADE:
        op.execute(statement)
