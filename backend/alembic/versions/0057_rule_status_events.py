"""T3.11.02 — journal of rule-set status changes.

Same shape and same reason as `role_grants` (0055): a published rule is a
checkable statement the platform makes about somebody else's law, so "who stood
behind this, and when" has to be answerable from the table. The status column
says where a set is now and nothing about how it got there.

The enum `rulestatus` already exists from 0054 and is reused — declared with
`create_type=False` so this migration does not try to create it a second time.
That is the one thing worth getting right here: an `sa.Enum` in a column
definition creates the type by default, and the second CREATE TYPE fails the
whole upgrade.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rule_status = postgresql.ENUM(
        "draft", "review", "published", "outdated",
        name="rulestatus",
        create_type=False,
    )
    op.create_table(
        "rule_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Null on the row that records creation: there was no status before it.
        sa.Column("from_status", rule_status, nullable=True),
        sa.Column("to_status", rule_status, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
    )
    op.create_index(
        "ix_rule_status_events_set", "rule_status_events", ["rule_set_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_rule_status_events_set", table_name="rule_status_events")
    op.drop_table("rule_status_events")
    # `rulestatus` is NOT dropped here — it belongs to 0054 and `rule_sets`
    # still uses it. Dropping a type another table depends on is how a
    # downgrade takes the schema with it.
