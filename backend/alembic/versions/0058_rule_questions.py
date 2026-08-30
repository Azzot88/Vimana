"""T3.11.05 — the questions layer over a rule set.

A corpus written as law is checkable and unreadable. `rule_questions` is the
second reading of the same text: what a person actually asks, answered in three
lines, with `section_anchor` pointing at the section that carries the verbatim
quotation. The pointer is the reason the answer is allowed to be short, so the
column is NOT NULL and publication is blocked when it resolves to nothing.

No enum is created or reused here — the table has none — so unlike 0057 there
is nothing to guard with `create_type=False`.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anchor", sa.String(length=64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locale", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        # Not a foreign key: it points at `rule_sections.anchor`, which is
        # unique only together with locale, and the question in Russian must be
        # able to point at a section that exists so far only in English.
        # Resolution is checked at the publication gate instead.
        sa.Column("section_anchor", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"]),
        sa.UniqueConstraint(
            "rule_set_id", "anchor", "locale", name="uq_rule_questions_anchor"
        ),
    )
    op.create_index(
        "ix_rule_questions_render", "rule_questions", ["rule_set_id", "locale", "order"]
    )


def downgrade() -> None:
    op.drop_index("ix_rule_questions_render", table_name="rule_questions")
    op.drop_table("rule_questions")
