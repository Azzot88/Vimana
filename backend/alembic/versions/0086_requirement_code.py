"""T3.11.09 — which line of the corridor checklist a document closes.

On the attachment rather than in the card's payload. A card is never edited in
this protocol (`CardState.superseded` is how a correction looks), so ticks kept
in a payload would need a new card per document — a wall of cards for one
parcel. Here the state is **derived**: an item is closed when an attachment on
the deal carries its code, which leaves one source of truth and nothing to keep
in step.

Free text, not a foreign key: the code comes from a `DocumentRequirement` inside
a snapshot that may since have been superseded, and a constraint pointing at a
live row would break the moment a rule was republished.

Revision ID: 0086
Revises: 0085
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op


revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments", sa.Column("requirement_code", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_attachments_requirement_code", "attachments", ["requirement_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_requirement_code", table_name="attachments")
    op.drop_column("attachments", "requirement_code")
