"""Peer Identity Verification (T2.1 MVP)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-17

Adds 5 tables + `users.highest_verification_level`. All enums created with
plain-string `CREATE TYPE` so migration is idempotent under re-runs.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


ENUMS = [
    ("verificationlevel", ["auto", "peer", "kyc"]),
    (
        "verificationrequeststatus",
        [
            "pending", "later_in_person", "declined", "declined_polite",
            "verified", "escalated",
        ],
    ),
    ("verificationtargetrole", ["sender", "carrier"]),
    ("sanctionsstatus", ["clean", "match", "review_needed"]),
    ("ownerrole", ["sender", "carrier", "both"]),
    ("storagemode", ["encrypted_blob", "zk_snark"]),
    ("verificationsource", ["auto_ocr", "peer", "arbiter_review", "kyc_provider"]),
]


def _ensure_enum(bind, name, values):
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :n"), {"n": name}
    ).fetchone()
    if exists:
        return
    inner = ", ".join(f"'{v}'" for v in values)
    bind.execute(sa.text(f"CREATE TYPE {name} AS ENUM ({inner})"))


def _table_exists(bind, name: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :n"
        ),
        {"n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    for name, values in ENUMS:
        _ensure_enum(bind, name, values)

    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS highest_verification_level VARCHAR(10)"
    )

    if not _table_exists(bind, "identity_containers"):
        op.execute(
            """
            CREATE TABLE identity_containers (
                id UUID PRIMARY KEY,
                owner_id UUID NOT NULL REFERENCES users(id),
                owner_role ownerrole NOT NULL DEFAULT 'both',
                storage_mode storagemode NOT NULL DEFAULT 'encrypted_blob',
                blob_encrypted BYTEA NOT NULL,
                blob_nonce BYTEA NOT NULL,
                doc_hash VARCHAR(64) NOT NULL,
                doc_country VARCHAR(2),
                doc_type VARCHAR(32),
                sanctions_check_status sanctionsstatus NOT NULL DEFAULT 'clean',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    if not _table_exists(bind, "verification_requests"):
        op.execute(
            """
            CREATE TABLE verification_requests (
                id UUID PRIMARY KEY,
                deal_id UUID NOT NULL REFERENCES deals(id),
                requested_by_id UUID NOT NULL REFERENCES users(id),
                target_role verificationtargetrole NOT NULL,
                status verificationrequeststatus NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            )
            """
        )

    if not _table_exists(bind, "verification_badges"):
        op.execute(
            """
            CREATE TABLE verification_badges (
                id UUID PRIMARY KEY,
                subject_id UUID NOT NULL REFERENCES users(id),
                level verificationlevel NOT NULL,
                source verificationsource NOT NULL,
                container_ref_id UUID REFERENCES identity_containers(id),
                verified_by_id UUID REFERENCES users(id),
                in_deal_id UUID REFERENCES deals(id),
                verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ
            )
            """
        )
        op.execute(
            "CREATE INDEX idx_verification_badges_subject_active "
            "ON verification_badges(subject_id, level) WHERE revoked_at IS NULL"
        )

    if not _table_exists(bind, "sanctions_list"):
        op.execute(
            """
            CREATE TABLE sanctions_list (
                id SERIAL PRIMARY KEY,
                source VARCHAR(32) NOT NULL,
                name_normalized VARCHAR(255) NOT NULL,
                dob VARCHAR(10),
                country VARCHAR(2),
                added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        op.execute(
            "CREATE INDEX idx_sanctions_list_name ON sanctions_list(name_normalized)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS verification_badges")
    op.execute("DROP TABLE IF EXISTS verification_requests")
    op.execute("DROP TABLE IF EXISTS identity_containers")
    op.execute("DROP TABLE IF EXISTS sanctions_list")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS highest_verification_level")
    for name, _ in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
