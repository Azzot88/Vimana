"""T3.11.07 — when the flight lands.

Owner's decision 2026-09-06: the trip form asks for the arrival time at the
**end of the route**. That is the time a sender actually needs — when the parcel
can be collected — and until now the model could only say when the carrier left.

On the leg rather than on the trip, because a chain has a landing per hop and
this is where one belongs; the form asks only for the last one, and the rest
stay `NULL`. Nullable is not a compromise: 29.8 % of real posts state a
departure hour at all, so a landing time the carrier does not know is not one
they should be made to invent — and every trip published before this revision
has none.

Revision ID: 0071
Revises: 0070
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trip_legs",
        sa.Column("arrive_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trip_legs", "arrive_at")
