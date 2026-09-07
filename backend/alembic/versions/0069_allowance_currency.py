"""T3.11.07 — the customs allowance gets a currency of its own.

Owner's decision 2026-09-06: the free-allowance field on the trip form is
edited with a currency beside it. It cannot be `Trip.currency`. A customs
allowance is denominated by the country the parcel lands in — $2 000 into the
US, €430 into the EU — while the price is whatever the carrier quotes in, and
those are routinely two different currencies. Sharing one column would mean
that choosing the allowance's currency silently re-prices the trip.

`NULL` means "the trip's currency", which is the common case: a carrier working
one corridor quotes and counts the allowance in the same money, and a column
defaulted to `USD` would put a currency on every trip whose carrier never chose
one.

`VARCHAR(4)`, matching `trips.currency` since 0068 — `USDT` and `USDC` are four
characters.

Revision ID: 0069
Revises: 0068
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("max_declared_value_currency", sa.String(length=4), nullable=True),
    )


def downgrade() -> None:
    # Nothing to preserve: every row that had a value here can only have said
    # something the trip's own currency could not, and there is no column left
    # to say it in.
    op.drop_column("trips", "max_declared_value_currency")
