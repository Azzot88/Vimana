"""T3.11.16 — bumping is withdrawn. Expiry stays.

Owner's decision, 2026-09-07: «не нужно поднимать рейсы… То что происходит в
чате, эти механики не должны приезжать на платформу.»

`0077` added freshness, a quota and a bump journal because the market holds
listings at the top by reposting. That reasoning describes a **feed**, and the
board is not one: a listing here is a plan with a date, and it is found by
route and by day rather than by whatever was touched last. Importing the habit
would have made attention buyable by pressing a button — which is the mechanic
the owner is refusing, not the implementation of it.

So `trips.listed_at` and `trip_bumps` go, along with the endpoint and the
button. **`trips.expires_at` stays**: that was the other half of `0077` and a
different thing entirely — a trip whose last flight has left is not a listing
anybody can act on, and hiding it needs no product opinion.

Dropped rather than left in place. A column nothing writes and a table nothing
reads are an invitation to the next author to «finish» a feature that was
turned down.

Revision ID: 0078
Revises: 0077
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_trip_bumps_trip", table_name="trip_bumps")
    op.drop_index("ix_trip_bumps_carrier_created", table_name="trip_bumps")
    op.drop_table("trip_bumps")
    op.drop_index("ix_trips_listed_at", table_name="trips")
    op.drop_column("trips", "listed_at")


def downgrade() -> None:
    op.add_column(
        "trips",
        sa.Column(
            "listed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("UPDATE trips SET listed_at = created_at")
    op.create_index("ix_trips_listed_at", "trips", ["listed_at"])
    op.create_table(
        "trip_bumps",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "trip_id",
            sa.UUID(),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "carrier_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_trip_bumps_carrier_created", "trip_bumps", ["carrier_id", "created_at"]
    )
    op.create_index("ix_trip_bumps_trip", "trip_bumps", ["trip_id"])
