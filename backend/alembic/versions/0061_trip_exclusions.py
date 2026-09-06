"""T3.11.07 — what the carrier will not take, from a closed list.

Only 5.9 % of real posts state exclusions at all (TASKS.md, «Разбор переписок
рынка»), and when they do the wording is nearly always one of five things:
cigarettes, alcohol, tobacco, food, luxury goods. Cigarettes and tobacco are one
refusal written two ways, so the vocabulary has five entries, not six.

A closed list rather than free text because a filter has to read it: today a
sender cannot tell "не беру сигареты", "сигареты не беру!" and "~~сигареты~~"
apart, and neither can a query. `carriage_rules` stays exactly as it is — it
carries everything the list does not.

JSON rather than an array column or a join table: it is a short set of literals
read whole with the trip, never queried by element, and the sibling columns
added in 0059 (`handover_origin`, `handover_destination`) are shaped the same
way. Nullable, and NULL means "said nothing", which is what 94 % of the market
does — an empty list would claim the carrier considered the question.

Revision ID: 0061
Revises: 0060
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("excluded", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "excluded")
