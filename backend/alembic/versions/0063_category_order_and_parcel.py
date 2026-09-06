"""T3.11.07 — the two commonest words on this market had no category.

Measured over 15 128 messages (TASKS.md, «Разбор переписок рынка»), carriers
name: documents 86.2 %, **parcels ≈71 %**, **clothing and personal effects
34 %**, medicine 32.8 %, electronics 15 %, animals 9.1 %, gifts 8.8 %.

`parcel` and `clothing` were absent from the registry seeded in 0003. A carrier
writing «возьму посылки» — the second most common sentence on this market — had
nowhere to file it, and a sender searching for it had nothing to match. They are
added here.

`sort_order` decides the picker's order **only while every `usage_count` is
still zero**. The list is ordered `is_default DESC, usage_count DESC,
sort_order ASC, name_key`: as soon as this platform has traffic of its own, its
own numbers outrank the seed. A number rather than the tuple's position so that
a category added later can be placed without a migration that renumbers the
world; carrier-added ones default to 100 and land at the end.

Revision ID: 0063
Revises: 0062
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op


revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

# Mirrors `models.marketplace.DEFAULT_CATEGORIES`, in the same order.
SEEDED = (
    "document",
    "parcel",
    "clothing",
    "medicine",
    "electronics",
    "animal",
    "gift",
    "art",
    "other",
)


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
    )

    for position, key in enumerate(SEEDED):
        # `ON CONFLICT DO NOTHING` on insert, then a separate update: the two
        # new keys have to be created, and the seven existing ones only
        # reordered. Doing it as an upsert on `sort_order` would also reset a
        # category an operator had deliberately moved.
        op.execute(
            sa.text(
                "INSERT INTO categories (id, name_key, is_default, usage_count, "
                "sort_order, created_at) "
                "VALUES (gen_random_uuid(), :key, true, 0, :pos, now()) "
                "ON CONFLICT (name_key) DO NOTHING"
            ).bindparams(key=key, pos=position)
        )
        op.execute(
            sa.text(
                "UPDATE categories SET sort_order = :pos WHERE name_key = :key"
            ).bindparams(key=key, pos=position)
        )


def downgrade() -> None:
    # The two new categories are not deleted: trips published in between may
    # reference them in `allowed_categories`, and removing the row would leave
    # those listings pointing at a key with no label.
    op.drop_column("categories", "sort_order")
