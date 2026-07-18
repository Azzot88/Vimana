"""route_notes + platform_notices (T_UX.2)

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
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
    _ensure_enum(
        bind, "routestatus", ["standard", "attention", "complex", "restricted"]
    )
    _ensure_enum(bind, "noticeseverity", ["info", "warning", "alert"])
    _ensure_enum(
        bind, "noticesurface", ["footer", "trip_card", "deal_page", "all"]
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS route_notes (
            id UUID PRIMARY KEY,
            origin_iso VARCHAR(3) NOT NULL,
            destination_iso VARCHAR(3) NOT NULL,
            status routestatus NOT NULL DEFAULT 'standard',
            severity noticeseverity NOT NULL DEFAULT 'info',
            headline_i18n_key VARCHAR(100) NOT NULL,
            body_i18n_key VARCHAR(100) NOT NULL,
            active_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            active_until TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_route_notes_origin ON route_notes(origin_iso)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_route_notes_destination ON route_notes(destination_iso)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_notices (
            id UUID PRIMARY KEY,
            key VARCHAR(100) UNIQUE NOT NULL,
            severity noticeseverity NOT NULL DEFAULT 'info',
            target_surface noticesurface NOT NULL DEFAULT 'all',
            active_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            active_until TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_notices")
    op.execute("DROP TABLE IF EXISTS route_notes")
    op.execute("DROP TYPE IF EXISTS noticesurface")
    op.execute("DROP TYPE IF EXISTS noticeseverity")
    op.execute("DROP TYPE IF EXISTS routestatus")
