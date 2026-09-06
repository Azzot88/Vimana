"""T3.11.07 — services around the flight, the settlement model, and cash out.

Three changes, all from the market analysis in TASKS.md, «Разбор переписок
рынка».

1. `services` — what the carrier does *around* the flight rather than on it.
   Onward shipping inside the destination country appears in 44.9 % of real
   posts, marketplace pickup in 19 %, buying goods to order in 18 %, door
   delivery in 8 %, photo reports in 1.7 %. None of it was expressible, so a
   sender looking for "will post it on from New York" had no way to search.

2. `payment_model` — how the carrier expects to be paid. A concrete sum appears
   in 0.1 % of posts; the settlement model appears in 61.7 % ("без предоплаты"
   42.6, "оплата при получении" 19.1). The model, not the number, is what this
   market actually states, and until now the model had nowhere to live.
   Nullable: "did not say" is not `on_delivery`, however common that answer is.

3. `money` leaves the exclusions vocabulary (owner's decision 2026-09-06). The
   platform takes no position on cash in either direction — neither a ban nor an
   advertised option — and a carrier with something to say about it says it in
   the trip's free-text description. It existed only between 0061 and this
   revision, so the cleanup below touches at most a few hours of rows, but it is
   written to run correctly against any of them.

Revision ID: 0062
Revises: 0061
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("services", sa.JSON(), nullable=True))
    op.add_column(
        "trips", sa.Column("payment_model", sa.String(length=16), nullable=True)
    )
    op.create_check_constraint(
        "ck_trips_payment_model",
        "trips",
        "payment_model IS NULL OR payment_model IN ('on_delivery','escrow','prepaid')",
    )

    # Strip `money` from stored exclusions. Rebuilt element by element rather
    # than pattern-matched on the serialised text: `excluded` is a JSON array
    # and a string replace over it would also hit a value that merely contains
    # the word.
    op.execute(
        """
        UPDATE trips
        SET excluded = (
            SELECT COALESCE(json_agg(value), '[]'::json)
            FROM json_array_elements_text(excluded) AS value
            WHERE value <> 'money'
        )
        WHERE excluded IS NOT NULL
          AND excluded::text LIKE '%money%'
        """
    )
    # A list that held nothing but `money` is now empty, and an empty list is a
    # claim the carrier considered exclusions and had none. They did not.
    op.execute("UPDATE trips SET excluded = NULL WHERE excluded::text = '[]'")


def downgrade() -> None:
    # `money` is not put back: the values were removed, and inventing them again
    # would be inventing refusals nobody made.
    op.drop_constraint("ck_trips_payment_model", "trips", type_="check")
    op.drop_column("trips", "payment_model")
    op.drop_column("trips", "services")
