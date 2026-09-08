"""T3.11.27 — the picture of what is being sent, taken before anybody agrees.

Owner's decision 2026-09-07: «Фото или ссылка на товар — на этапе условий: "вот
что я отправляю", перевозчик видит до согласия». The link half already exists
(`terms.cargo_url`); this is the other half.

One enum value, no tables. Its own kind rather than `doc` because an arbiter
reads these labels: this is the only photograph in a deal's record taken while
the deal could still be refused, and filing it as a generic document loses
exactly that. The same slot is what a buy-and-carry deal will use for the item
being bought (`T3.11.17` part 2).

Revision ID: 0083
Revises: 0082
Create Date: 2026-09-07
"""
from alembic import op


revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction (0006 pattern).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE attachmentkind ADD VALUE IF NOT EXISTS 'cargo_photo'")


def downgrade() -> None:
    # Postgres enum values cannot be removed; extra values are harmless.
    pass
