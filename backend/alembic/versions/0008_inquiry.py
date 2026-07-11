"""Trip inquiry chat threads + encrypted messages (T1.22)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    has_inquiries = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'trip_inquiries'"
        )
    ).fetchone()
    if not has_inquiries:
        op.execute(
            """
            CREATE TABLE trip_inquiries (
                id UUID PRIMARY KEY,
                trip_id UUID NOT NULL REFERENCES trips(id),
                sender_id UUID NOT NULL REFERENCES users(id),
                carrier_id UUID NOT NULL REFERENCES users(id),
                deal_id UUID REFERENCES deals(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_trip_inquiries_trip_sender UNIQUE (trip_id, sender_id)
            )
            """
        )

    has_messages = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'inquiry_messages'"
        )
    ).fetchone()
    if not has_messages:
        op.execute(
            """
            CREATE TABLE inquiry_messages (
                id UUID PRIMARY KEY,
                inquiry_id UUID NOT NULL REFERENCES trip_inquiries(id),
                sender_id UUID NOT NULL REFERENCES users(id),
                text_ciphertext BYTEA,
                text_nonce BYTEA,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inquiry_messages")
    op.execute("DROP TABLE IF EXISTS trip_inquiries")
