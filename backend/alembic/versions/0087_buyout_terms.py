"""T3.11.18 — «выкуплю товар» cannot be offered without its two answers.

The scheme is quoted verbatim in the market dump: «Сначала просит зубную щётку
выкупить, а потом ирригатор! По итогу оплачиваешь щётку, доставку, а на
следующий день…». What is at risk is the **carrier's** money — two thousand
dollars of bought goods against a fifty-dollar carriage fee — and 42.6 % «без
предоплаты» is not generosity, it is a position taken by people who have been
asked for money up front.

So a trip offering `purchase_on_request` must also state a ceiling and who pays
for the goods. Both columns are nullable, because most trips do not offer the
service; the pairing is enforced by `TripCreate`, which is the only place that
can see the services list and the two fields at once.

Until Фаза 5 there is no money on the platform: this is a declared limit and a
record, never a guarantee (`§9.1`).

Revision ID: 0087
Revises: 0086
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op


revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("buyout_limit", sa.Float(), nullable=True))
    op.add_column("trips", sa.Column("buyout_paid_by", sa.String(24), nullable=True))
    op.create_check_constraint(
        "ck_trips_buyout_paid_by",
        "trips",
        "buyout_paid_by IS NULL OR "
        "buyout_paid_by IN ('sender_prepaid','carrier_credit')",
    )
    op.create_check_constraint(
        "ck_trips_buyout_limit", "trips", "buyout_limit IS NULL OR buyout_limit > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_trips_buyout_limit", "trips", type_="check")
    op.drop_constraint("ck_trips_buyout_paid_by", "trips", type_="check")
    op.drop_column("trips", "buyout_paid_by")
    op.drop_column("trips", "buyout_limit")
