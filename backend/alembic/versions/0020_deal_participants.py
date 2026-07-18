"""DealParticipant (T3.3 — recipient role)

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _ensure_enum(bind, name, values):
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :n"), {"n": name}
    ).fetchone()
    if exists:
        return
    inner = ", ".join(f"'{v}'" for v in values)
    bind.execute(sa.text(f"CREATE TYPE {name} AS ENUM ({inner})"))


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_enum(bind, "dealparticipantrole", ["recipient"])

    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='deal_participants'"
        )
    ).fetchone()
    if not exists:
        op.execute(
            """
            CREATE TABLE deal_participants (
                id UUID PRIMARY KEY,
                deal_id UUID NOT NULL REFERENCES deals(id),
                user_id UUID REFERENCES users(id),
                role dealparticipantrole NOT NULL DEFAULT 'recipient',
                invited_by UUID NOT NULL REFERENCES users(id),
                invite_token VARCHAR(64) NOT NULL UNIQUE,
                invited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                CONSTRAINT uq_participant_deal_user_role UNIQUE (deal_id, user_id, role)
            )
            """
        )
        op.execute(
            "CREATE INDEX idx_deal_participants_active "
            "ON deal_participants(deal_id) WHERE revoked_at IS NULL"
        )
        op.execute(
            "CREATE INDEX idx_deal_participants_token "
            "ON deal_participants(invite_token)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_participants")
    op.execute("DROP TYPE IF EXISTS dealparticipantrole")
