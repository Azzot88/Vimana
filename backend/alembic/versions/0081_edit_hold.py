"""T3.11.27 — who is editing the agreement right now.

Owner's rule, 2026-09-07: «две минуты — это окно для правки, пока другой ждёт;
если справился раньше — молодец, нет — запускай ещё раз».

The hold is taken **before** the change and released by it. The first attempt
inverted that — it treated a freshly submitted proposal as an open window — and
so every proposal froze the other side for two minutes at exactly the moment
they were meant to answer it. Five tests said so on the first run.

Two columns on `deals` rather than a table of holds: a hold is one fact about
one deal, it never needs history, and it expires by comparison rather than by a
sweeper that has to run.

Revision ID: 0081
Revises: 0080
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deals",
        sa.Column(
            "edit_hold_by_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "deals",
        sa.Column("edit_hold_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deals", "edit_hold_until")
    op.drop_column("deals", "edit_hold_by_id")
