"""T3.34 — the card type becomes a column instead of a prefix in the text.

**The backfill is the point of this migration.** T1.26 shipped the shared
address as a system message whose text starts with `📍 SHARED ADDRESS`, and the
frontend recognised it by parsing that string back out. Adding the column
without converting existing rows would leave every already-shared address
rendering as raw text the moment the frontend switches to reading `card_kind` —
a silent regression in old deals, which are exactly the ones nobody re-opens to
check.

So the prefix is read once, here, and written into `card_kind`. The text itself
is left untouched: it still carries the address, the card still renders from it,
and the encrypted column keeps whatever encryption it already had. Only the
recognition moves.

Rows are matched on the encrypted-text column being absent from the predicate —
the text is AES-GCM at rest, so SQL cannot see the prefix. The conversion
therefore runs in Python over the system messages, which are a small minority of
the table.

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

SHARED_ADDRESS_PREFIX = "📍 SHARED ADDRESS"

# `create_type=False` plus an explicit `.create()` below. `op.add_column` does
# NOT emit CREATE TYPE for an enum — only `create_table` does — so a bare
# `sa.Enum(...)` here fails with `type "cardstate" does not exist`.
card_state = postgresql.ENUM(
    "pending", "accepted", "declined", "expired", "superseded",
    name="cardstate", create_type=False,
)
card_ack_role = postgresql.ENUM(
    "sender", "carrier", "recipient", "operator",
    name="cardackrole", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    card_state.create(bind, checkfirst=True)
    card_ack_role.create(bind, checkfirst=True)

    op.add_column(
        "deal_vault_messages",
        sa.Column("card_kind", sa.String(length=48), nullable=True),
    )
    op.add_column(
        "deal_vault_messages",
        sa.Column("card_payload", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "deal_vault_messages",
        sa.Column("card_state", card_state, nullable=True),
    )
    op.add_column(
        "deal_vault_messages",
        sa.Column("requires_ack_by", card_ack_role, nullable=True),
    )
    op.add_column(
        "deal_vault_messages",
        sa.Column("acked_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "deal_vault_messages",
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "deal_vault_messages",
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_deal_vault_messages_card_kind", "deal_vault_messages", ["card_kind"]
    )
    op.create_foreign_key(
        "fk_deal_vault_messages_acked_by",
        "deal_vault_messages", "users", ["acked_by_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_deal_vault_messages_supersedes",
        "deal_vault_messages", "deal_vault_messages", ["supersedes_id"], ["id"],
    )

    _backfill_shared_addresses()


def _backfill_shared_addresses() -> None:
    """Type the addresses shared before this migration existed."""
    from app.core.crypto import decrypt  # imported late: app config need not load for DDL

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, text_ciphertext, text_nonce FROM deal_vault_messages "
            "WHERE is_system = true AND text_ciphertext IS NOT NULL "
            "AND text_nonce IS NOT NULL AND is_e2e = false"
        )
    ).fetchall()

    converted = []
    for row in rows:
        try:
            plain = decrypt(bytes(row.text_nonce), bytes(row.text_ciphertext))
        except Exception:
            # A message we cannot read is a message we must not reclassify.
            continue
        if plain and plain.startswith(SHARED_ADDRESS_PREFIX):
            converted.append(row.id)

    for msg_id in converted:
        bind.execute(
            sa.text(
                "UPDATE deal_vault_messages SET card_kind = 'address.shared' WHERE id = :id"
            ),
            {"id": msg_id},
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_deal_vault_messages_supersedes", "deal_vault_messages", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_deal_vault_messages_acked_by", "deal_vault_messages", type_="foreignkey"
    )
    op.drop_index("ix_deal_vault_messages_card_kind", table_name="deal_vault_messages")
    for column in (
        "supersedes_id", "acked_at", "acked_by_id",
        "requires_ack_by", "card_state", "card_payload", "card_kind",
    ):
        op.drop_column("deal_vault_messages", column)
    card_ack_role.drop(op.get_bind(), checkfirst=True)
    card_state.drop(op.get_bind(), checkfirst=True)
