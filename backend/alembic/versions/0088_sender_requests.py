"""T3.11.19 — «кто летит в ближайшие дни ЛА — Москва?» becomes a row.

**366 posts in the market dump take this shape.** It is not a failure to use the
board: at a five-day median horizon the sender is right, because at the moment
they look the trip they need does not exist yet. A listing answers a question
about the present; a request answers one about next week.

Deliberately not an `Order`. An order is half of a deal — declared value,
recipient, category, a trip it is matched to — and every one of those is a
decision this sender has not made. Filing the request as an order would mean
inventing four answers so the row would save, and a matching engine would then
read them as though somebody had given them.

Revision ID: 0088
Revises: 0087
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op


revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sender_requests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("sender_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("origin", sa.String(100), nullable=False),
        sa.Column("destination", sa.String(100), nullable=False),
        sa.Column("window_from", sa.Date(), nullable=False),
        sa.Column("window_to", sa.Date(), nullable=False),
        sa.Column("what", sa.String(300), nullable=True),
        sa.Column(
            "notify", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_open", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_sender_requests_mine", "sender_requests", ["sender_id", "created_at"]
    )
    # The hot read: «who is waiting for this corridor», run on every publication.
    # Leads with the corridor and carries the window so the match is one index
    # scan rather than a filter over everybody's requests.
    op.create_index(
        "ix_sender_requests_corridor",
        "sender_requests",
        ["origin", "destination", "window_to", "is_open"],
    )


def downgrade() -> None:
    op.drop_index("ix_sender_requests_corridor", table_name="sender_requests")
    op.drop_index("ix_sender_requests_mine", table_name="sender_requests")
    op.drop_table("sender_requests")
