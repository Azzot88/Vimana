"""T3.11.07 — how this carrier can be paid, written once.

Owner's decision 2026-09-06: «Как со мной рассчитаться» is chosen from what the
carrier has added rather than retyped on every trip. «Наличные при встрече»,
«перевод на карту Каспи», «Зелле» — the same three or four answers each time,
and the trip form offered only a free-text box beside a country-derived
catalogue.

Free strings, not codes, and deliberately so: what people transfer through is
local and changes faster than a vocabulary we could ship, and a carrier naming
one we had not heard of would be told they are wrong. `payment_systems` on the
trip is free text for exactly this reason; this column is the carrier's own
shortlist of it.

An array rather than a set because order is the carrier's — the first is what
they offer first — the same argument as `default_currencies` in 0068.

`VARCHAR(60)`: long enough for «перевод на карту Каспи», short enough that the
field cannot become a note. Empty by default, and an empty list is a real
answer: "I have not said".

Revision ID: 0070
Revises: 0069
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "payment_methods",
            sa.ARRAY(sa.String(length=60)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "payment_methods")
