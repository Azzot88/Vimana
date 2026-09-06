"""T3.11.07 — the currency an account prices in, chosen once.

A display preference by the same argument as `unit_weight` and `date_format`
beside it: a carrier working one corridor quotes in one currency for years, and
re-picking it on every publication is a field that is always answered the same
way. The trip form pre-fills from it instead of hard-coding USD.

Not a rate and not a conversion. `Trip.currency` still stores what the carrier
published in, and nothing here converts anything — the preference decides what
the empty form starts with, and nothing else.

USD as the default because the corridor this launches on is UAE ↔ US, and
because it is what the column it replaces already defaulted to in the form.

Revision ID: 0067
Revises: 0066
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "default_currency")
