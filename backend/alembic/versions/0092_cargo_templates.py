"""T3.12.03 pt.2 — cargo templates.

`D-CARGO-MODEL`: a sender's description of cargo, filled in at the response to
a trip and kept in the cabinet; copied into a cargo as a snapshot. Several per
person, each named (owner, 2026-09-14). Goes with its owner.

Revision ID: 0092
Revises: 0091
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cargo_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("declared_value", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_cargo_templates_owner_id", "cargo_templates", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cargo_templates_owner_id", table_name="cargo_templates")
    op.drop_table("cargo_templates")
