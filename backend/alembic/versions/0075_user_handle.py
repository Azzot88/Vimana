"""T3.11.24 — a handle to be found by.

Owner's request, 2026-09-07: «в кабинете должна быть возможность выбрать handle
типа "@***"», alongside lookup by the email and phone already in the cabinet.

Display names cannot do this job: they are not unique and should not become
unique — two people called Igor are two people called Igor, and renaming the
second one to keep a search working is the wrong trade. The handle is the
identifier: unique, stored lowercase so `@Igor` and `@igor` cannot become two
accounts, nullable because nobody is stopped from using the platform for want of
one.

32 characters, matching what people are used to elsewhere; the shape itself
(letters, digits, underscore, at least three) is enforced in the schema rather
than by a CHECK, because the rule will be adjusted by product feel and a CHECK
would make each adjustment a migration with a table lock.

Revision ID: 0075
Revises: 0074
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("handle", sa.String(length=32), nullable=True))
    op.create_index("ix_users_handle", "users", ["handle"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_handle", table_name="users")
    op.drop_column("users", "handle")
