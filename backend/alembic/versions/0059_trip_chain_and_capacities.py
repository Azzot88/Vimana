"""T3.11.15 — the trip becomes a chain, and capacity becomes two capacities.

Three changes, all driven by the analysis of 15 128 real marketplace messages
recorded in TASKS.md, block «Разбор переписок рынка (2026-09-06)».

1. `trip_legs` — an ordered list of flights. 36.6 % of carrier posts carry two
   or more dates and 15.0 % three or more cities, so a single
   origin/destination/depart_at triple is wrong for a third of the market, not
   for an edge case. Existing trips are backfilled into a one-leg chain, which
   is exactly what they mean.

2. Two capacities on `trips`. `capacity` stays the kilograms; `space_kind` and
   `size_hint` say what kind of room it is (weight in kg appears in 2.4 % of
   posts, "small / not big" in 9.9 %), and `declared_value_status` says whether
   the customs allowance is spent — carriers report it as a balance
   ("лимит на люкс уже занят") while still taking documents on the same flight.

3. `handover_origin` / `handover_destination` **replace**
   `allowed_handover_methods`. Accepting and handing over are asymmetric in
   practice: "in Italy I take it at my address or meet in Milan, Turin, Genoa;
   in Russia I accept a courier at home", and one combined list cannot say that.
   The old column is dropped rather than left alongside: with both ends stated
   separately it becomes a second way to say the same thing, and the next reader
   would have to be told which one wins.

The vocabularies are enforced by CHECK constraints rather than PostgreSQL enums:
they are short lists that will grow, and adding a value to an enum type in
Postgres is a migration with a lock, while adding one here is a constraint swap.

Revision ID: 0059
Revises: 0058
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column(
            "declared_value_status",
            sa.String(length=10),
            nullable=False,
            server_default="open",
        ),
    )
    op.add_column(
        "trips",
        sa.Column(
            "space_kind",
            sa.String(length=16),
            nullable=False,
            server_default="unspecified",
        ),
    )
    op.add_column("trips", sa.Column("size_hint", sa.String(length=8), nullable=True))
    op.add_column("trips", sa.Column("handover_origin", sa.JSON(), nullable=True))
    op.add_column("trips", sa.Column("handover_destination", sa.JSON(), nullable=True))

    # Carried over, not discarded: a carrier who listed the methods they accept
    # meant them for the pick-up end, which is the end they were describing.
    op.execute(
        """
        UPDATE trips
        SET handover_origin = json_build_object(
            'methods', allowed_handover_methods, 'points', json_build_array()
        )
        WHERE allowed_handover_methods IS NOT NULL
        """
    )
    op.drop_column("trips", "allowed_handover_methods")

    op.create_check_constraint(
        "ck_trips_space_kind",
        "trips",
        "space_kind IN ('cabin','checked_partial','checked_full','unspecified')",
    )
    op.create_check_constraint(
        "ck_trips_size_hint",
        "trips",
        "size_hint IS NULL OR size_hint IN ('small','medium','large')",
    )
    op.create_check_constraint(
        "ck_trips_declared_value_status",
        "trips",
        "declared_value_status IN ('open','exhausted')",
    )

    op.create_table(
        "trip_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        # `leg_order`, not `order`: the bare word is reserved in SQL and works
        # only for as long as every reader remembers to quote it.
        sa.Column("leg_order", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=100), nullable=False),
        sa.Column("destination", sa.String(length=100), nullable=False),
        sa.Column("depart_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "flown_by", sa.String(length=8), nullable=False, server_default="self"
        ),
        sa.PrimaryKeyConstraint("id"),
        # CASCADE: a leg without its trip is not a record of anything, and the
        # trip row is the thing every other table points at.
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("trip_id", "leg_order", name="uq_trip_legs_order"),
        sa.CheckConstraint("leg_order >= 0", name="ck_trip_legs_order_nonneg"),
        sa.CheckConstraint("origin <> destination", name="ck_trip_legs_distinct"),
        sa.CheckConstraint(
            "flown_by IN ('self','proxy')", name="ck_trip_legs_flown_by"
        ),
    )
    op.create_index("ix_trip_legs_trip_order", "trip_legs", ["trip_id", "leg_order"])

    # Backfill. Every existing trip is a one-leg chain — that is what its three
    # columns already say — and leaving them without legs would make the API
    # return an empty chain for a trip that has a route.
    op.execute(
        """
        INSERT INTO trip_legs (id, trip_id, leg_order, origin, destination,
                               depart_at, flown_by)
        SELECT gen_random_uuid(), id, 0, origin, destination, depart_at, 'self'
        FROM trips
        WHERE origin <> destination
        """
    )


def downgrade() -> None:
    op.drop_index("ix_trip_legs_trip_order", table_name="trip_legs")
    op.drop_table("trip_legs")
    op.drop_constraint("ck_trips_declared_value_status", "trips", type_="check")
    op.drop_constraint("ck_trips_size_hint", "trips", type_="check")
    op.drop_constraint("ck_trips_space_kind", "trips", type_="check")
    op.add_column(
        "trips", sa.Column("allowed_handover_methods", sa.JSON(), nullable=True)
    )
    op.execute(
        """
        UPDATE trips
        SET allowed_handover_methods = handover_origin -> 'methods'
        WHERE handover_origin IS NOT NULL
        """
    )
    op.drop_column("trips", "handover_destination")
    op.drop_column("trips", "handover_origin")
    op.drop_column("trips", "size_hint")
    op.drop_column("trips", "space_kind")
    op.drop_column("trips", "declared_value_status")
