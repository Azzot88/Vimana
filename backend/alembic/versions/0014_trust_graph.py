"""Trust Graph (T2.4)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
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
    _ensure_enum(bind, "trustedgekind", ["peer_verified", "dealt_with", "invited"])

    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verifications_issued_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verifications_received_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS dealt_with_count INTEGER NOT NULL DEFAULT 0"
    )

    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'trust_edges'"
        )
    ).fetchone()
    if not exists:
        op.execute(
            """
            CREATE TABLE trust_edges (
                id UUID PRIMARY KEY,
                from_user_id UUID NOT NULL REFERENCES users(id),
                to_user_id UUID NOT NULL REFERENCES users(id),
                kind trustedgekind NOT NULL,
                weight FLOAT NOT NULL DEFAULT 1.0,
                source_ref VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMPTZ,
                CONSTRAINT uq_trust_edge_pair_kind_source
                    UNIQUE (from_user_id, to_user_id, kind, source_ref)
            )
            """
        )
        op.execute(
            "CREATE INDEX idx_trust_edges_from_active "
            "ON trust_edges(from_user_id, kind) WHERE revoked_at IS NULL"
        )
        op.execute(
            "CREATE INDEX idx_trust_edges_to_active "
            "ON trust_edges(to_user_id, kind) WHERE revoked_at IS NULL"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trust_edges")
    op.execute("DROP TYPE IF EXISTS trustedgekind")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS dealt_with_count")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS verifications_received_count")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS verifications_issued_count")
