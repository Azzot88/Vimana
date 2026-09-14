"""T3.12.02 — the role is called Arbiter.

«Роли "Оператор" не существует» (owner, 2026-09-13, `D-CARGO-MODEL`). The word
lived in two places the database keeps: a value of the `cardackrole` enum that
no card in the catalogue ever used, and the name of the grants table through
which an arbiter reads a disputed vault.

Both are **renamed, not recreated**. A renamed enum value keeps every row that
holds it; a renamed table keeps its grants, its unique constraint and its
partial index. Dropping and recreating would have been the same schema and a
lost record of who let the arbiter in.

Guarded both ways, so a database that already went through the rename — or a
test database fixed by `conftest` — is left alone rather than failing on a
value or a table that is not there.

Revision ID: 0089
Revises: 0088
Create Date: 2026-09-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def _enum_has(bind, label: str) -> bool:
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'cardackrole' AND e.enumlabel = :label"
            ),
            {"label": label},
        ).fetchone()
        is not None
    )


def _table_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = :name"
            ),
            {"name": name},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _enum_has(bind, "operator"):
        op.execute("ALTER TYPE cardackrole RENAME VALUE 'operator' TO 'arbiter'")
    if _table_exists(bind, "operator_access_grants") and not _table_exists(
        bind, "arbiter_access_grants"
    ):
        op.execute("ALTER TABLE operator_access_grants RENAME TO arbiter_access_grants")


def downgrade() -> None:
    bind = op.get_bind()
    if _enum_has(bind, "arbiter"):
        op.execute("ALTER TYPE cardackrole RENAME VALUE 'arbiter' TO 'operator'")
    if _table_exists(bind, "arbiter_access_grants") and not _table_exists(
        bind, "operator_access_grants"
    ):
        op.execute("ALTER TABLE arbiter_access_grants RENAME TO operator_access_grants")
