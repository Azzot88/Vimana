"""T3.11.07 — meeting places and payment methods get a country.

Owner's decision 2026-09-06: what a carrier keeps in their profile is filed
under a country, because that is what the trip form filters on. Receiving
addresses already had `country_iso`; these two did not, and the cost showed up
in the form — a Moscow landmark offered to somebody arriving in Dubai, Каспи
offered on a Warsaw route. A list that has to be read and rejected on every
publication is worse than no list, which is the opposite of why these lists
exist.

`meeting_places` gains `country_iso` and `city`. The city is here and not on the
payment methods on purpose: «у метро Фили» is only findable if you know it is
Moscow, and one carrier meets people in two cities of one country often enough
for the country alone to be too coarse a filter.

`users.payment_methods` goes from `VARCHAR(60)[]` to `JSONB`, each entry
`{"name": …, "country": …}`. Existing entries are carried over with a `null`
country, which means «anywhere» — not a gap: «наличные при встрече» is genuinely
country-agnostic, and a row written before the field existed made no claim about
where it applies.

Both new columns are **nullable**, and only because rows predate them. The
request schemas require a country on every new meeting place; a place whose
country is unknown is offered on every route, which is what those rows already
did.

Revision ID: 0072
Revises: 0071
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meeting_places", sa.Column("country_iso", sa.String(length=2), nullable=True)
    )
    op.add_column(
        "meeting_places", sa.Column("city", sa.String(length=150), nullable=True)
    )

    # Converted in place rather than dropped and re-added: the column shipped
    # hours ago and may already hold somebody's shortlist. `unnest` turns each
    # text element into an object; an empty array stays an empty array, which
    # `COALESCE` is there for — `json_agg` over no rows is NULL, and the column
    # is NOT NULL.
    op.execute("ALTER TABLE users ALTER COLUMN payment_methods DROP DEFAULT")
    op.execute(
        "ALTER TABLE users ALTER COLUMN payment_methods TYPE JSONB USING ("
        "  COALESCE("
        "    (SELECT jsonb_agg(jsonb_build_object('name', m, 'country', NULL))"
        "     FROM unnest(payment_methods) AS m),"
        "    '[]'::jsonb"
        "  )"
        ")"
    )
    op.execute("ALTER TABLE users ALTER COLUMN payment_methods SET DEFAULT '[]'::jsonb")


def downgrade() -> None:
    # The country is dropped on the way back — there is nowhere in a text array
    # to put it. The names survive, which is the half a downgraded build can use.
    op.execute("ALTER TABLE users ALTER COLUMN payment_methods DROP DEFAULT")
    op.execute(
        "ALTER TABLE users ALTER COLUMN payment_methods TYPE VARCHAR(60)[] USING ("
        "  COALESCE("
        "    (SELECT array_agg(elem->>'name')"
        "     FROM jsonb_array_elements(payment_methods) AS elem),"
        "    '{}'::VARCHAR(60)[]"
        "  )"
        ")"
    )
    op.execute("ALTER TABLE users ALTER COLUMN payment_methods SET DEFAULT '{}'")

    op.drop_column("meeting_places", "city")
    op.drop_column("meeting_places", "country_iso")
