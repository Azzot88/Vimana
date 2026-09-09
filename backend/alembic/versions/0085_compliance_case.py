"""T3.11.06 — the checklist a person actually got, kept as a snapshot.

`user_id` is nullable because the wizard runs **before registration**: the
corpus is free information, and a sign-up wall in front of free information is a
sign-up form pretending to be a service.

`checklist` is a frozen copy rather than a query re-run on read. Publishing a new
version of a rule must not rewrite the list under somebody already standing in a
queue with the old one — the same principle as `carriage_rules` copied into a
trip (`T_UX.15`) and terms frozen at handover (`MASTERPLAN §4.1`). `attrs` is
stored beside it because the snapshot alone cannot be re-derived: the same
corridor answered differently is a different list.

Revision ID: 0085
Revises: 0084
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op


revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_cases",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("destination", sa.String(16), nullable=False),
        sa.Column("transit", sa.JSON(), nullable=True),
        sa.Column("category_key", sa.String(50), nullable=False),
        sa.Column("attrs", sa.JSON(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("depart_at", sa.Date(), nullable=True),
        sa.Column("trip_id", sa.UUID(), sa.ForeignKey("trips.id"), nullable=True),
        sa.Column("deal_id", sa.UUID(), sa.ForeignKey("deals.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_compliance_cases_user", "compliance_cases", ["user_id", "created_at"]
    )
    op.create_index("ix_compliance_cases_deal", "compliance_cases", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_compliance_cases_deal", table_name="compliance_cases")
    op.drop_index("ix_compliance_cases_user", table_name="compliance_cases")
    op.drop_table("compliance_cases")
