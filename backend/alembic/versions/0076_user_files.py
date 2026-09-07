"""T3.11.25 — the personal file safe.

Owner's statement, 2026-09-07: «файлы из одной сделки с этим аккаунтом доступны
и для новых сделок и уже там должны присутствовать». Until now an `Attachment`
hung off a `message_id` and nothing else, so a passport sent for one parcel was
sent again for the next and the two copies were unrelated bytes as far as the
platform could tell.

- `user_files` — one row per (owner, hash). The same document uploaded twice is
  one file: the hash identifies it, and a second row would give «впервые
  предоставлен» two answers.
- `attachments.user_file_id` — which safe entry an attachment came from.
  Nullable, and left null for everything uploaded before today: those rows are
  not wrong, they predate the question. No backfill for the same reason `0026`
  gave — inventing a first-provided date for old bytes would put the first
  untrue value into the column the table exists to make trustworthy.
- `file_reattached` on the event enum. **Not** a synonym for `file_added`: the
  bytes were provided in March under a different parcel, and a record saying
  they were provided here would be false in the one place this product exists
  to keep true.

Revision ID: 0076
Revises: 0075
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction (0006 pattern).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS 'file_reattached'"
        )

    op.create_table(
        "user_files",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("r2_key", sa.String(length=512), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            # `postgresql.ENUM`, not `sa.Enum`: `create_type=False` is a
            # PostgreSQL-dialect option, and the generic type accepts the
            # keyword without honouring it — so the first run tried to
            # `CREATE TYPE attachmentkind` again and died on a type that has
            # existed since `0003`. The column points at the existing type;
            # `0079` is what adds a value to it.
            postgresql.ENUM(
                "handoff_photo",
                "receipt_photo",
                "doc",
                "payment_receipt",
                "identity_doc",
                name="attachmentkind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "scan_status",
            sa.String(length=10),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("owner_id", "file_hash", name="uq_user_files_owner_hash"),
    )
    op.create_index("ix_user_files_owner", "user_files", ["owner_id"])

    op.add_column(
        "attachments",
        sa.Column(
            "user_file_id",
            sa.UUID(),
            sa.ForeignKey("user_files.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_attachments_user_file_id", "attachments", ["user_file_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_user_file_id", table_name="attachments")
    op.drop_column("attachments", "user_file_id")
    op.drop_index("ix_user_files_owner", table_name="user_files")
    op.drop_table("user_files")
    # Postgres enum values cannot be removed; the extra value is harmless.
