"""T3.11.24 — contacts have a tier, and closeness is mutual or it is nothing.

Owner's definition, 2026-09-07: «Контакты — они же Connections — просто
знакомые… Близкие — Close, это те кому доверяешь. Контакты могут быть и
односторонними, Близкие только двухсторонние.»

The table already stored a **directed** row: `user_id` keeps
`connected_user_id`. One column is therefore enough for both halves of the
model — the tier is directed too, and a pair is close only when both of its rows
say so. The alternative, a `closeness` table keyed by the ordered pair, would
have had to answer «who asked first» with a second column anyway, and would have
put the same fact in two places.

`connection` for every existing row: rows written by invite acceptance are
acquaintances by construction, and promoting them wholesale would hand every
early user a list of «close» people they never chose.

Revision ID: 0074
Revises: 0073
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "connections",
        sa.Column(
            "tier",
            sa.String(length=16),
            nullable=False,
            server_default="connection",
        ),
    )
    # A recipient picked out of the contacts list was never invited: the sender
    # named an account that already exists, and the participant row is written
    # accepted. `NOT NULL` here would have forced a token nobody ever sends —
    # a live credential minted to satisfy a constraint, and a column claiming
    # this person arrived through a link.
    op.alter_column("deal_participants", "invite_token", nullable=True)


def downgrade() -> None:
    op.alter_column("deal_participants", "invite_token", nullable=False)
    op.drop_column("connections", "tier")
