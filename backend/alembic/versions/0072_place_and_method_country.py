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

    # Through a second column rather than `ALTER ... TYPE ... USING`, and not by
    # choice: Postgres refuses a **subquery in a transform expression**
    # (`FeatureNotSupportedError: cannot use subquery in transform expression`),
    # and turning one text element into one JSON object needs `unnest` — which
    # is a subquery however it is written. An `UPDATE` has no such restriction,
    # so the value is moved rather than cast.
    #
    # The old column is not dropped and re-added under the same name: the column
    # shipped hours ago and may already hold somebody's shortlist, and this way
    # the data is carried across instead of reset.
    #
    # `COALESCE` is for the empty array — `jsonb_agg` over no rows is NULL and
    # the column is NOT NULL.
    op.execute(
        "ALTER TABLE users ADD COLUMN payment_methods_jsonb JSONB "
        "NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "UPDATE users SET payment_methods_jsonb = COALESCE("
        "  (SELECT jsonb_agg(jsonb_build_object('name', m, 'country', NULL))"
        "   FROM unnest(payment_methods) AS m),"
        "  '[]'::jsonb"
        ")"
    )
    op.execute("ALTER TABLE users DROP COLUMN payment_methods")
    op.execute(
        "ALTER TABLE users RENAME COLUMN payment_methods_jsonb TO payment_methods"
    )


def downgrade() -> None:
    # The country is dropped on the way back — there is nowhere in a text array
    # to put it. The names survive, which is the half a downgraded build can use.
    #
    # Through a second column for the same reason as the upgrade: the transform
    # needs `jsonb_array_elements`, and a subquery is not allowed in `USING`.
    op.execute(
        "ALTER TABLE users ADD COLUMN payment_methods_text VARCHAR(60)[] "
        "NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "UPDATE users SET payment_methods_text = COALESCE("
        "  (SELECT array_agg(elem->>'name')"
        "   FROM jsonb_array_elements(payment_methods) AS elem),"
        "  '{}'::VARCHAR(60)[]"
        ")"
    )
    op.execute("ALTER TABLE users DROP COLUMN payment_methods")
    op.execute(
        "ALTER TABLE users RENAME COLUMN payment_methods_text TO payment_methods"
    )

    op.drop_column("meeting_places", "city")
    op.drop_column("meeting_places", "country_iso")
