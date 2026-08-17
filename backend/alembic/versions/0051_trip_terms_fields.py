"""T3.35 — a trip gets a price.

Until now `trips` carried a route, a date and a capacity, and no price at all —
so every deal had to invent one in chat, and nothing was comparable between two
trips on the same corridor. These columns are the carrier's published baseline;
the sender may still counter in chat, and both paths normalise to the same
shape.

All nullable, no backfill: a trip published before this migration has no stated
price, and inventing one for it would put words in a carrier's mouth. The UI
shows "price on request" for those, which is what they actually are.

`currency` is the exception — it defaults to USD rather than NULL, because a
number without a currency is not a price, and every existing declared value in
`orders` already defaults the same way.

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("price_per_kg", sa.Float(), nullable=True))
    op.add_column("trips", sa.Column("min_deal_price", sa.Float(), nullable=True))
    op.add_column(
        "trips",
        sa.Column(
            "currency", sa.String(length=3), nullable=False, server_default="USD"
        ),
    )
    op.add_column(
        "trips", sa.Column("allowed_handover_methods", sa.JSON(), nullable=True)
    )
    op.add_column("trips", sa.Column("max_declared_value", sa.Float(), nullable=True))
    op.add_column("trips", sa.Column("bond_tier", sa.String(length=16), nullable=True))


def downgrade() -> None:
    for column in (
        "bond_tier",
        "max_declared_value",
        "allowed_handover_methods",
        "currency",
        "min_deal_price",
        "price_per_kg",
    ):
        op.drop_column("trips", column)
