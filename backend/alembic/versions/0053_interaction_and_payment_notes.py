"""T_UX.21 — the two standing notes a carrier writes once and sends in chat.

`interaction_rules` is how this carrier works: how fast they answer, what they
want in the chat straight away, what they do not do. `payment_instructions` is
how to settle with them — an account number, a wallet, "cash on handover".

Both are **text and only text**, and that is the decision, not a shortcut. The
catalogue of payment methods (HodlHodl-style: a table of methods plus the
carrier's selection) was deferred by the owner: the platform moves no money
today — cards are Фаза 4, escrow is Фаза 5, and neither is started — so a
catalogue would be a schema shaped around a mechanism that does not exist yet.
When payments arrive the catalogue joins them, and this column stays as the
free-text remainder every payment page still needs.

Consequence to keep in sight while these are only text: nothing here is
validated, matched or enforced by the platform, so no screen may word them as
if it were. `DESIGNGUIDELINES §9.1` — the copy says "how to settle with me",
never "payment on the platform".

Both sit on `users` and, unlike `carriage_rules` (T_UX.15), are **not** copied
onto the trip. They describe the person rather than the shipment: an answer time
that changed in March should read as the current one in a chat opened in March,
which is the opposite of what a carriage rule needs.

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-23
"""
import sqlalchemy as sa
from alembic import op


revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("interaction_rules", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("payment_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "payment_instructions")
    op.drop_column("users", "interaction_rules")
