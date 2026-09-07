"""T3.11.07 — an account prices in several currencies, not one.

Owner's decision 2026-09-06, one revision after 0067 introduced the single
value. A carrier working two corridors quotes in two currencies, and one who
settles in a stablecoin quotes in that as well; asking them to pick one and
retype the others on every trip is asking the wrong question.

`default_currency VARCHAR(3)` becomes `default_currencies VARCHAR(4)[]`.
**Order is meaningful**: the first entry is what a new trip starts in, the
rest are offered beside it. That is why this is an array and not a set, and
why it is not two columns — a "primary" plus a bag of "others" would be two
fields for one idea, and the second would drift from the first.

Backfilled from the old column, so nobody loses the choice they already made.
`VARCHAR(4)` rather than 3 because `USDT` and `USDC` are four characters, which
is also why 0067's column could not simply be widened in place and kept.

The same four characters have to fit where the money actually lands, so
`trips.currency` and `orders.currency` are widened here too. Without that, a
carrier whose primary currency is a stablecoin would pick it in the profile and
then be refused by the publish form — the setting would exist and do nothing.
`rule_requirements.currency` is left at three: it is the cost of a customs
formality, authored by compliance editors from the account's list, and no path
writes a four-character code into it.

Revision ID: 0068
Revises: 0067
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_currencies",
            sa.ARRAY(sa.String(length=4)),
            nullable=False,
            server_default="{USD}",
        ),
    )
    # Carry the single choice over rather than resetting everybody to USD: 0067
    # shipped, and somebody may already have set theirs.
    op.execute(
        "UPDATE users SET default_currencies = ARRAY[default_currency] "
        "WHERE default_currency IS NOT NULL AND default_currency <> ''"
    )
    op.drop_column("users", "default_currency")

    for table in ("trips", "orders"):
        op.alter_column(
            table,
            "currency",
            existing_type=sa.String(length=3),
            type_=sa.String(length=4),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Narrowed before the data could ever be four characters long, so a stored
    # `USDT` has to go somewhere rather than be truncated into `USD` — a code
    # that means a different thing.
    for table in ("trips", "orders"):
        op.execute(f"UPDATE {table} SET currency = 'USD' WHERE length(currency) > 3")
        op.alter_column(
            table,
            "currency",
            existing_type=sa.String(length=4),
            type_=sa.String(length=3),
            existing_nullable=False,
        )

    op.add_column(
        "users",
        sa.Column(
            "default_currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
    )
    # The first entry is the primary one, so it is the honest thing to keep.
    # A four-character code has no home in a three-character column and falls
    # back to USD rather than being silently truncated into a code that does
    # not exist.
    op.execute(
        "UPDATE users SET default_currency = CASE "
        "WHEN array_length(default_currencies, 1) >= 1 "
        " AND length(default_currencies[1]) = 3 THEN default_currencies[1] "
        "ELSE 'USD' END"
    )
    op.drop_column("users", "default_currencies")
