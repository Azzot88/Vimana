"""T3.11.07 — settlement has two models, not three (owner's correction).

`on_platform · cash_on_delivery · transfer_on_delivery` → `on_platform ·
off_platform`.

The middle version was wrong, and the reason is worth writing down: cash is not
a peer of "transfer". It is **one of the systems** people settle in outside the
platform, alongside a bank app, a remittance service or a stablecoin. Listing it
as a model made the form ask "cash or transfer?" — which is the same question as
"which system?", asked twice and answerable inconsistently.

So the model says only whether the money touches the platform, and
`payment_systems` — already there since 0064 — says through what when it does
not. `cash` is now the first entry of the payment-systems catalogue rather than
a value of this column.

Both old off-platform values map to `off_platform`; nothing is lost, because the
distinction they carried now lives in the systems list. `on_platform` is
unchanged.

Revision ID: 0066
Revises: 0065
Create Date: 2026-09-06
"""
from alembic import op


revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_trips_payment_model", "trips", type_="check")
    op.execute(
        "UPDATE trips SET payment_model = 'off_platform' "
        "WHERE payment_model IN ('cash_on_delivery', 'transfer_on_delivery')"
    )
    op.create_check_constraint(
        "ck_trips_payment_model",
        "trips",
        "payment_model IS NULL OR payment_model IN ('on_platform','off_platform')",
    )


def downgrade() -> None:
    # `off_platform` becomes `cash_on_delivery`: cash is what the overwhelming
    # majority of this market means by settling outside the platform (96
    # mentions against 23 for everything else combined), so it is the least
    # wrong of the two old values. The systems list keeps the real answer either
    # way.
    op.drop_constraint("ck_trips_payment_model", "trips", type_="check")
    op.execute(
        "UPDATE trips SET payment_model = 'cash_on_delivery' "
        "WHERE payment_model = 'off_platform'"
    )
    op.create_check_constraint(
        "ck_trips_payment_model",
        "trips",
        "payment_model IS NULL OR payment_model IN "
        "('on_platform','cash_on_delivery','transfer_on_delivery')",
    )
