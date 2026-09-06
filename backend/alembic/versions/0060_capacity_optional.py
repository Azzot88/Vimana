"""T3.11.07 — the express path: weight stops being required to publish.

The market this product copies publishes late. Measured over 15 128 messages
(TASKS.md, «Разбор переписок рынка»): the median carrier posts **five days**
before departure, **31 % inside two days** and **11.8 % on the day of the
flight**. Against that horizon every required field is a toll, and this one is
the field the market does not answer: weight in kilograms appears in **2.4 %**
of posts, while "small / not big" appears in 9.9 % — which is what `size_hint`
(0059) is for.

So `capacity` becomes nullable. NULL means "not stated", which is a real answer
and a different one from a number; nothing is backfilled, because every existing
row has a figure its carrier actually typed.

Nothing else in the schema changes. Readers were already null-tolerant where it
counted — `api/trust` sums with `capacity or 0.0` — and the ones that were not
are fixed in the same commit.

Revision ID: 0060
Revises: 0059
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("trips", "capacity", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # A trip published without a weight has no weight to restore, and the column
    # cannot go back to NOT NULL while such rows exist. Zero is the only value
    # that is not a claim about the bag: it reads as "nothing fits", which is
    # wrong, but any positive number would be a figure nobody typed.
    op.execute("UPDATE trips SET capacity = 0 WHERE capacity IS NULL")
    op.alter_column("trips", "capacity", existing_type=sa.Float(), nullable=False)
