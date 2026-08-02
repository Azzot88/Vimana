"""T3.18 — how much of an identity is public.

Three values, and the difference between them is what a stranger can learn:

- `full`    — the identity page renders: name, avatar, activity level, trust
              counters, verification, first activity. The default, because a
              marketplace where nobody can look anybody up is a marketplace
              where nobody deals.
- `minimal` — existence and verification level only. Enough to confirm "this
              key is a real participant" without a portrait.
- `hidden`  — 404 to everyone but the owner.

Default `full` for existing accounts: they were already visible through the
metric endpoints, and quietly hiding everyone would change the product under
its users rather than give them a choice.

The setting governs **every** public slice, not just the page — see
`core/permissions.visible_to`. A setting that hides the page while the numbers
stay readable by direct request is a setting that lies.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-01
"""
from alembic import op


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS public_profile VARCHAR(16) "
        "NOT NULL DEFAULT 'full'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS public_profile")
