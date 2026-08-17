"""T_UX.14 / T_UX.15 — display preferences and standing carriage rules.

Both defaults are chosen rather than inherited. `kg` and `eu` are what the
starting corridor (UAE ↔ US) reads on the sending end and what the rest of the
product already prints; an account that never opens the setting gets the same
figures it saw yesterday.

Deliberately **not** derived from the browser locale. A carrier flying between
metric and imperial countries thinks in one of them, and that does not change
with the device they happen to open the site on — a preference guessed per
session is one that keeps guessing wrong.

`carriage_rules` lands on **both** `users` and `trips`, and that is not
duplication: the user row is the template the carrier edits, the trip row is the
copy taken when the trip was published. Referencing instead of copying would let
a rule edited in March rewrite what a sender agreed to in February.

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "unit_weight", sa.String(length=4), nullable=False, server_default="kg"
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "date_format", sa.String(length=2), nullable=False, server_default="eu"
        ),
    )
    op.add_column("users", sa.Column("carriage_rules", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("carriage_rules", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "carriage_rules")
    op.drop_column("users", "carriage_rules")
    op.drop_column("users", "date_format")
    op.drop_column("users", "unit_weight")
