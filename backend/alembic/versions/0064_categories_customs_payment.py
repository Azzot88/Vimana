"""T3.11.07 — three corrections from the owner's review of the form (2026-09-06).

**1. The picker offers seven categories, in the market's order.**
`document · clothing · electronics · medicine · animal · art · other`.
`parcel` and `gift` are retired. `parcel` was added the same morning off the
market analysis — ≈71 % of posts say «возьму посылки» — and taken back out
because a parcel is the *container*, not the cargo: everything on this market is
a parcel, so as a category it says nothing and would be ticked by everyone. The
frequency was real, the conclusion was wrong.

Retired, not deleted. Real trips carry `gift` in `allowed_categories` since
0003, and deleting the row would leave those listings pointing at a key with
nothing behind it. `is_active` is a separate flag from `is_default` on purpose:
`is_default` means "shipped with the product" and stays true for both. One flag
carrying both meanings would lose the difference the first time somebody asked
why `gift` is still in the table.

**2. `declared_value_status` is dropped.**
The column held `open | exhausted` beside `max_declared_value`. Once the number
means the allowance *left* — which is what the field is now labelled — zero
already says "spent", and a separate state is a second place for the same fact
to be wrong. It lived from 0059 to here.

**3. The settlement vocabulary is replaced.**
`on_delivery · escrow · prepaid` → `on_platform · cash_on_delivery ·
transfer_on_delivery`, plus `payment_systems` for the transfer case. The old
list mixed two questions — *when* money moves and *through what* — and the
market answers both, separately.

Old values are mapped, not discarded: `on_delivery` is cash after delivery in
all but name, and `escrow` is settlement on the platform. `prepaid` has no
equivalent in the new list — money before the flight is not one of the three
offered — so those rows are set to NULL, which is the honest answer: "the
carrier said something we no longer ask".

Revision ID: 0064
Revises: 0063
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

ACTIVE = (
    "document",
    "clothing",
    "electronics",
    "medicine",
    "animal",
    "art",
    "other",
)
RETIRED = ("parcel", "gift")


def upgrade() -> None:
    # ── categories ────────────────────────────────────────────────────────
    op.add_column(
        "categories",
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default="true"
        ),
    )
    for position, key in enumerate(ACTIVE):
        op.execute(
            sa.text(
                "INSERT INTO categories (id, name_key, is_default, usage_count, "
                "sort_order, is_active, created_at) "
                "VALUES (gen_random_uuid(), :key, true, 0, :pos, true, now()) "
                "ON CONFLICT (name_key) DO NOTHING"
            ).bindparams(key=key, pos=position)
        )
        op.execute(
            sa.text(
                "UPDATE categories SET sort_order = :pos, is_active = true "
                "WHERE name_key = :key"
            ).bindparams(key=key, pos=position)
        )
    for key in RETIRED:
        op.execute(
            sa.text(
                "UPDATE categories SET is_active = false WHERE name_key = :key"
            ).bindparams(key=key)
        )

    # ── customs allowance ─────────────────────────────────────────────────
    op.drop_constraint("ck_trips_declared_value_status", "trips", type_="check")
    op.drop_column("trips", "declared_value_status")

    # ── settlement ────────────────────────────────────────────────────────
    op.add_column("trips", sa.Column("payment_systems", sa.JSON(), nullable=True))
    op.drop_constraint("ck_trips_payment_model", "trips", type_="check")
    op.alter_column(
        "trips",
        "payment_model",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
    )
    op.execute(
        "UPDATE trips SET payment_model = CASE payment_model "
        "WHEN 'on_delivery' THEN 'cash_on_delivery' "
        "WHEN 'escrow' THEN 'on_platform' "
        "ELSE NULL END "
        "WHERE payment_model IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_trips_payment_model",
        "trips",
        "payment_model IS NULL OR payment_model IN "
        "('on_platform','cash_on_delivery','transfer_on_delivery')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_trips_payment_model", "trips", type_="check")
    op.execute(
        "UPDATE trips SET payment_model = CASE payment_model "
        "WHEN 'cash_on_delivery' THEN 'on_delivery' "
        "WHEN 'on_platform' THEN 'escrow' "
        "ELSE NULL END "
        "WHERE payment_model IS NOT NULL"
    )
    op.alter_column(
        "trips",
        "payment_model",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
    )
    op.create_check_constraint(
        "ck_trips_payment_model",
        "trips",
        "payment_model IS NULL OR payment_model IN ('on_delivery','escrow','prepaid')",
    )
    op.drop_column("trips", "payment_systems")

    op.add_column(
        "trips",
        sa.Column(
            "declared_value_status",
            sa.String(length=10),
            nullable=False,
            server_default="open",
        ),
    )
    op.create_check_constraint(
        "ck_trips_declared_value_status",
        "trips",
        "declared_value_status IN ('open','exhausted')",
    )
    op.drop_column("categories", "is_active")
