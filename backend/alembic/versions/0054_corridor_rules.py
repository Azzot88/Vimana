"""T3.11.01 — corridor rules: jurisdictions, rule sets, sources, requirements.

No rule data is seeded. An empty corpus is the correct starting state: a rule
without a cited source must not exist, and inventing one here to make the screen
look populated would be exactly the failure the `rule_sources` table is built to
prevent.

Two structural notes.

**`uq_rule_sets_published` is partial.** Older versions stay in the table — the
archive is what makes "what did this say in March" answerable — so the constraint
can only cover rows in the published state. A plain unique constraint would
forbid history.

**Jurisdictions are seeded, rules are not.** The codes below are the founding
corridor RU → transit → US → state, and they are structure rather than legal
claim: nothing in a country code needs a citation. The list is deliberately
short — states and cities arrive with the corpus that needs them (T3.11.04).

`art` joins the category registry seeded in 0003. `ON CONFLICT DO NOTHING`
because a database that already has an editor-created `art` row is a normal
database, not a broken one.

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-29
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


JURISDICTIONS = [
    ("RU", "country", None, "Russia"),
    ("US", "country", None, "United States"),
    ("TR-IST", "transit_point", None, "Istanbul (transit)"),
    ("AE-DXB", "transit_point", None, "Dubai (transit)"),
]


def upgrade() -> None:
    op.create_table(
        "jurisdictions",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "country", "subdivision", "city", "transit_point",
                name="jurisdictionkind",
            ),
            nullable=False,
        ),
        sa.Column("parent_code", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code"),
        sa.ForeignKeyConstraint(["parent_code"], ["jurisdictions.code"]),
    )
    op.create_index("ix_jurisdictions_parent_code", "jurisdictions", ["parent_code"])

    op.create_table(
        "rule_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("export", "import", "transit", name="ruledirection"),
            nullable=False,
        ),
        sa.Column("jurisdiction_code", sa.String(length=16), nullable=False),
        sa.Column("category_key", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.Enum("draft", "review", "published", "outdated", name="rulestatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("title", sa.String(length=300), nullable=False, server_default=""),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "needs_review", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["jurisdiction_code"], ["jurisdictions.code"]),
        sa.ForeignKeyConstraint(["category_key"], ["categories.name_key"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.UniqueConstraint(
            "direction", "jurisdiction_code", "category_key", "version",
            name="uq_rule_sets_version",
        ),
    )
    op.create_index("ix_rule_sets_category_key", "rule_sets", ["category_key"])
    op.create_index("ix_rule_sets_status", "rule_sets", ["status"])
    op.create_index("ix_rule_sets_needs_review", "rule_sets", ["needs_review"])
    op.create_index(
        "ix_rule_sets_lookup",
        "rule_sets",
        ["category_key", "direction", "jurisdiction_code"],
    )
    op.create_index(
        "uq_rule_sets_published",
        "rule_sets",
        ["direction", "jurisdiction_code", "category_key"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "rule_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anchor", sa.String(length=64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locale", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("title", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"]),
        sa.UniqueConstraint(
            "rule_set_id", "anchor", "locale", name="uq_rule_sections_anchor"
        ),
    )
    op.create_index(
        "ix_rule_sections_render", "rule_sections", ["rule_set_id", "locale", "order"]
    )

    op.create_table(
        "rule_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authority", sa.String(length=200), nullable=False),
        sa.Column("document_title", sa.String(length=500), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["section_id"], ["rule_sections.id"]),
    )
    op.create_index("ix_rule_sources_section", "rule_sources", ["section_id"])

    op.create_table(
        "document_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("issuer", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "obtained_by",
            sa.Enum("sender", "carrier", "recipient", name="obtainedby"),
            nullable=False,
            server_default="sender",
        ),
        sa.Column(
            "is_mandatory", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("condition", sa.JSON(), nullable=True),
        sa.Column("valid_for_days", sa.Integer(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"]),
        sa.UniqueConstraint(
            "rule_set_id", "code", name="uq_document_requirements_code"
        ),
    )
    op.create_index("ix_document_requirements_code", "document_requirements", ["code"])

    for code, kind, parent, name in JURISDICTIONS:
        op.execute(
            sa.text(
                "INSERT INTO jurisdictions (code, kind, parent_code, name, created_at) "
                "VALUES (:code, :kind, :parent, :name, now()) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, kind=kind, parent=parent, name=name)
        )

    op.execute(
        sa.text(
            "INSERT INTO categories (id, name_key, is_default, usage_count, created_at) "
            "VALUES (:id, 'art', true, 0, now()) "
            "ON CONFLICT (name_key) DO NOTHING"
        ).bindparams(id=uuid.uuid4())
    )


def downgrade() -> None:
    op.execute("DELETE FROM categories WHERE name_key = 'art'")

    op.drop_index("ix_document_requirements_code", table_name="document_requirements")
    op.drop_table("document_requirements")
    op.drop_index("ix_rule_sources_section", table_name="rule_sources")
    op.drop_table("rule_sources")
    op.drop_index("ix_rule_sections_render", table_name="rule_sections")
    op.drop_table("rule_sections")
    op.drop_index("uq_rule_sets_published", table_name="rule_sets")
    op.drop_index("ix_rule_sets_lookup", table_name="rule_sets")
    op.drop_index("ix_rule_sets_needs_review", table_name="rule_sets")
    op.drop_index("ix_rule_sets_status", table_name="rule_sets")
    op.drop_index("ix_rule_sets_category_key", table_name="rule_sets")
    op.drop_table("rule_sets")
    op.drop_index("ix_jurisdictions_parent_code", table_name="jurisdictions")
    op.drop_table("jurisdictions")

    # Enums are created implicitly by the columns above; dropping them keeps a
    # down-then-up cycle from failing on "type already exists".
    for name in ("obtainedby", "rulestatus", "ruledirection", "jurisdictionkind"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
