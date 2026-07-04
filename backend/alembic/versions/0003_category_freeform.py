"""category as freeform string + Category registry

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DEFAULT_CATEGORIES = ("document", "medicine", "electronics", "gift", "animal", "other")


def upgrade() -> None:
    op.execute("ALTER TABLE orders ALTER COLUMN category TYPE VARCHAR(50) USING category::text")
    op.execute("DROP TYPE IF EXISTS ordercategory")

    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name_key", sa.String(50), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name_key", name="uq_categories_name_key"),
    )
    op.create_index("ix_categories_name_key", "categories", ["name_key"])

    for key in DEFAULT_CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO categories (id, name_key, is_default, usage_count, created_at) "
                "VALUES (:id, :key, true, 0, now())"
            ).bindparams(id=uuid.uuid4(), key=key)
        )


def downgrade() -> None:
    op.drop_index("ix_categories_name_key", table_name="categories")
    op.drop_table("categories")
