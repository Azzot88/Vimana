"""T3.42 pt.2 — `users.role` becomes `users.roles`: roles add up.

One column held one role, so every grant was a silent revocation of the
previous one. An account is routinely both an arbiter and a rules editor —
different jobs, not a ladder — and the old shape could not say so.

**The old column is dropped, not kept in step.** Two columns describing the
same fact drift, and the one nobody remembers to write is the one everything
reads. `core/roles.py` is the single writer of the new column and appends a
`RoleGrant` row in the same transaction; `core/superuser.py` is the one
documented exception.

An ordinary account gets `{}`, not `{user}`: "member" is what you are when you
hold no role, and putting it in the list would turn "has this account been
given anything" into a question about the list's contents rather than its
length.

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default="{}",
        ),
    )
    # A single-element array for anybody who held something, empty for the rest.
    op.execute(
        "UPDATE users SET roles = ARRAY[role]::varchar[] "
        "WHERE role IS NOT NULL AND role <> 'user'"
    )
    op.drop_column("users", "role")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )
    # Lossy by nature, and deliberately explicit about which way it loses:
    # superuser outranks everything, then arbiter. An account that held two
    # roles comes back holding one, because that is all the old shape could
    # express. Recorded here so nobody reads a clean downgrade as a reversible
    # one.
    op.execute(
        "UPDATE users SET role = CASE "
        "WHEN 'superuser' = ANY(roles) THEN 'superuser' "
        "WHEN 'arbiter' = ANY(roles) THEN 'arbiter' "
        "WHEN array_length(roles, 1) IS NOT NULL THEN roles[1] "
        "ELSE 'user' END"
    )
    op.drop_column("users", "roles")
