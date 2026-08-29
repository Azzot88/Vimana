"""T3.42 — the journal that says where a role came from.

**Existing roles are backfilled, and the row says so.** Every account currently
holding `arbiter` gets an `accepted` row with a null actor and a reason naming
this migration. The alternative — an empty table — would have made the journal
lie by omission on its first day: a live arbiter with no history reads as a role
that came from nowhere, which is exactly the state this task exists to end.

The backfill cannot invent who granted it or when, and it does not pretend to:
`actor_id` is null and `created_at` is the migration's own timestamp. A row that
admits it is a reconstruction is worth more than a plausible one that is made up.

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


_BACKFILL_REASON = (
    "Backfilled by migration 0055: this account already held the role when the "
    "journal was introduced. The original grant predates any record."
)


def upgrade() -> None:
    op.create_table(
        "role_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "event",
            sa.Enum(
                "offered", "accepted", "declined", "revoked", name="rolegrantevent"
            ),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["subject_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
    )
    op.create_index("ix_role_grants_subject_id", "role_grants", ["subject_id"])
    op.create_index("ix_role_grants_created_at", "role_grants", ["created_at"])
    op.create_index(
        "ix_role_grants_subject_role",
        "role_grants",
        ["subject_id", "role", "created_at"],
    )

    # `gen_random_uuid()` rather than a Python-side uuid: this is one statement
    # over an unknown number of rows, and looping in the migration to generate
    # ids would trade a builtin for a slower version of itself. Available in
    # core Postgres since 13.
    #
    # `superuser` is excluded: User Zero is created by `core/superuser.py` at
    # startup, not granted by anybody, and a journal row would describe a
    # decision that was never made.
    op.execute(
        sa.text(
            "INSERT INTO role_grants "
            "(id, subject_id, role, event, actor_id, reason, created_at) "
            "SELECT gen_random_uuid(), id, role, "
            "       CAST('accepted' AS rolegrantevent), NULL, :reason, now() "
            "FROM users "
            "WHERE role IS NOT NULL AND role NOT IN ('user', 'superuser')"
        ).bindparams(reason=_BACKFILL_REASON)
    )


def downgrade() -> None:
    op.drop_index("ix_role_grants_subject_role", table_name="role_grants")
    op.drop_index("ix_role_grants_created_at", table_name="role_grants")
    op.drop_index("ix_role_grants_subject_id", table_name="role_grants")
    op.drop_table("role_grants")
    sa.Enum(name="rolegrantevent").drop(op.get_bind(), checkfirst=True)
