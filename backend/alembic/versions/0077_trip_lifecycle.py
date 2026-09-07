"""T3.11.16 — freshness, expiry and the bump journal.

The market analysis behind this: **60.8 % of carrier posts are a word-for-word
repost of the author's own text**, median interval 23 hours, and 49 % of authors
do it. The market does not create listings, it holds them at the top of the
feed. Arriving here without a mechanism, that habit becomes duplicate trips.

- `trips.listed_at` — how fresh the *listing* is, which is not when the row was
  written. Bumping moves this and nothing else, so the trip keeps its identity,
  its deals and its `created_at`. Backfilled from `created_at`: every existing
  trip is exactly as fresh as the day it was published, which is true.
- `trips.expires_at` — the departure of the **last** leg, denormalised the way
  `origin`/`destination`/`depart_at` are denormalised from the first. Backfilled
  from the legs where they exist and from `depart_at` where they do not; the
  board hides what has already flown without anybody pressing anything.
- `trip_bumps` — one row per press. Quota counter and journal in the same table
  on purpose: a limit nobody can audit is a limit nobody believes.

Revision ID: 0077
Revises: 0076
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column(
            "listed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Every trip is as fresh as the day it was published — true, and it keeps
    # the board's order identical to what it was before this revision.
    op.execute("UPDATE trips SET listed_at = created_at")
    op.create_index("ix_trips_listed_at", "trips", ["listed_at"])

    op.add_column(
        "trips", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The last leg's departure, or the trip's own when it has no legs (every
    # trip published before `0059`). Chains are short — the subquery is over a
    # handful of rows per trip.
    op.execute(
        "UPDATE trips SET expires_at = COALESCE("
        "  (SELECT MAX(depart_at) FROM trip_legs WHERE trip_legs.trip_id = trips.id),"
        "  depart_at)"
    )
    op.create_index("ix_trips_expires_at", "trips", ["expires_at"])

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


def downgrade() -> None:
    op.drop_index("ix_trip_bumps_trip", table_name="trip_bumps")
    op.drop_index("ix_trip_bumps_carrier_created", table_name="trip_bumps")
    op.drop_table("trip_bumps")
    op.drop_index("ix_trips_expires_at", table_name="trips")
    op.drop_column("trips", "expires_at")
    op.drop_index("ix_trips_listed_at", table_name="trips")
    op.drop_column("trips", "listed_at")
