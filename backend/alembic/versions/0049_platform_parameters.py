"""T3.40 — business-logic parameters out of the source and behind an audit.

No backfill. An empty table is the correct starting state: `app.core.params`
carries a default for every key, so a fresh database runs on the numbers written
in MASTERPLAN §4.1 rather than on nulls. Seeding rows here would create the
false impression that somebody chose them, which is exactly the distinction the
`source` field on the read model exists to preserve.

`effective_from` is indexed together with (key, scope) because resolution always
asks the same question — newest row for this key and scope that has already come
into force — and that is one range scan on the composite index.

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="global"),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column(
            "value_type",
            sa.Enum("percent", "decimal", "integer", "string", name="paramvaluetype"),
            nullable=False,
            server_default="decimal",
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_parameters_key", "platform_parameters", ["key"])
    op.create_index(
        "ix_platform_parameters_effective_from",
        "platform_parameters",
        ["effective_from"],
    )
    op.create_index(
        "ix_platform_parameters_key_scope_from",
        "platform_parameters",
        ["key", "scope", "effective_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_parameters_key_scope_from", table_name="platform_parameters")
    op.drop_index("ix_platform_parameters_effective_from", table_name="platform_parameters")
    op.drop_index("ix_platform_parameters_key", table_name="platform_parameters")
    op.drop_table("platform_parameters")
    # The enum is created implicitly by the column above; dropping it here keeps
    # a down-then-up cycle from failing on "type already exists".
    sa.Enum(name="paramvaluetype").drop(op.get_bind(), checkfirst=True)
