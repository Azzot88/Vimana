"""T3.11.23 — one chat per person, deals nested inside it.

Owner's model, 2026-09-07: «Чаты привязаны к пользователям и существуют в
единственном числе на человека. Сделок может быть много… Сделка это чат,
вложенный в чат.»

The nested chat already existed — `Deal` plus `DealVaultMessage` is exactly
that, one thread carrying both text and cards. What did not exist was the outer
one. `trip_inquiries` was keyed `(trip_id, sender_id)`, so writing to one
carrier about three trips produced three threads with the same person and none
of them was «our conversation».

What this revision does:

- `chats` — the pair, stored **ordered** (low id first) behind a unique index,
  so «one per person» is a fact of the database rather than a habit of the code.
- `chat_messages` — was `inquiry_messages`. Rows are carried over with their
  timestamps and their ciphertext untouched: the at-rest key does not change,
  so nothing is re-encrypted and nothing needs to be readable by this migration.
- `about_trip_id` on the message. This is how «рейс становится содержимым, а не
  личностью треда» survives contact with the carrier's panel, which counts how
  many people asked about a given trip: with one thread per person there is no
  per-trip thread left to count, so the trip moves onto the message. Backfilled
  from the old thread onto its **first** message — the one that opened the
  conversation, which is the one that was about the trip.
- `deals.chat_id` and `deals.shipment_no`.

**Threads fold, and that loses one thing.** Two conversations with the same
person about two trips become one, ordered by time. Which of them a *later*
message belonged to is not recoverable — the old model recorded it as «which
thread», and after the fold there is one. That is inherent to the merge, not an
oversight: the owner asked for one chat per person, and one chat per person is
what a fold produces.

Revision ID: 0073
Revises: 0072
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_low_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_high_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_chats_pair"),
        sa.CheckConstraint("user_low_id < user_high_id", name="ck_chats_pair_ordered"),
    )
    op.create_index("ix_chats_low", "chats", ["user_low_id"])
    op.create_index("ix_chats_high", "chats", ["user_high_id"])

    # One chat per distinct pair, whichever way round the old thread recorded
    # them. `LEAST`/`GREATEST` is what makes (A,B) and (B,A) the same pair, and
    # it is the same rule the `CHECK` above enforces from then on.
    op.execute(
        "INSERT INTO chats (id, user_low_id, user_high_id, created_at) "
        "SELECT gen_random_uuid(), pair.lo, pair.hi, pair.started FROM ("
        "  SELECT LEAST(sender_id, carrier_id) AS lo,"
        "         GREATEST(sender_id, carrier_id) AS hi,"
        "         MIN(created_at) AS started"
        "  FROM trip_inquiries"
        "  WHERE sender_id <> carrier_id"
        "  GROUP BY 1, 2"
        ") AS pair"
    )

    op.rename_table("inquiry_messages", "chat_messages")
    op.add_column(
        "chat_messages", sa.Column("chat_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "chat_messages",
        sa.Column("about_trip_id", sa.UUID(), sa.ForeignKey("trips.id"), nullable=True),
    )
    op.execute(
        "UPDATE chat_messages m SET chat_id = c.id "
        "FROM trip_inquiries i "
        "JOIN chats c ON c.user_low_id = LEAST(i.sender_id, i.carrier_id) "
        "            AND c.user_high_id = GREATEST(i.sender_id, i.carrier_id) "
        "WHERE m.inquiry_id = i.id"
    )
    # The trip lands on the message that opened the thread. A later message in
    # the same thread was not «about the trip» in any sense the sender would
    # recognise — it was a reply.
    op.execute(
        "UPDATE chat_messages m SET about_trip_id = i.trip_id "
        "FROM trip_inquiries i "
        "WHERE m.inquiry_id = i.id AND m.id = ("
        "  SELECT m2.id FROM chat_messages m2 WHERE m2.inquiry_id = i.id"
        "  ORDER BY m2.created_at, m2.id LIMIT 1"
        ")"
    )
    # Anything that could not be placed had no thread to belong to; there is no
    # honest chat to put it in and no reader who could find it.
    op.execute("DELETE FROM chat_messages WHERE chat_id IS NULL")
    op.alter_column("chat_messages", "chat_id", nullable=False)
    op.create_foreign_key(
        "fk_chat_messages_chat", "chat_messages", "chats", ["chat_id"], ["id"]
    )
    op.drop_index("ix_inquiry_messages_inquiry_created", table_name="chat_messages")
    op.drop_column("chat_messages", "inquiry_id")
    op.create_index(
        "ix_chat_messages_chat_created", "chat_messages", ["chat_id", "created_at", "id"]
    )
    op.create_index("ix_chat_messages_about_trip", "chat_messages", ["about_trip_id"])

    op.add_column("deals", sa.Column("chat_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_deals_chat", "deals", "chats", ["chat_id"], ["id"])
    op.create_index("ix_deals_chat_id", "deals", ["chat_id"])
    # Existing deals get their pair's chat, creating it where the two never
    # exchanged a message before matching — which is the ordinary path today,
    # since a deal could be struck straight off the board.
    op.execute(
        "INSERT INTO chats (id, user_low_id, user_high_id, created_at) "
        "SELECT gen_random_uuid(), pair.lo, pair.hi, pair.started FROM ("
        "  SELECT LEAST(sender_id, carrier_id) AS lo,"
        "         GREATEST(sender_id, carrier_id) AS hi,"
        "         MIN(created_at) AS started"
        "  FROM deals WHERE sender_id <> carrier_id GROUP BY 1, 2"
        ") AS pair "
        "ON CONFLICT (user_low_id, user_high_id) DO NOTHING"
    )
    op.execute(
        "UPDATE deals d SET chat_id = c.id FROM chats c "
        "WHERE c.user_low_id = LEAST(d.sender_id, d.carrier_id) "
        "  AND c.user_high_id = GREATEST(d.sender_id, d.carrier_id)"
    )

    op.add_column("deals", sa.Column("shipment_no", sa.String(length=12), nullable=True))
    op.create_index("ix_deals_shipment_no", "deals", ["shipment_no"], unique=True)

    op.drop_table("trip_inquiries")


def downgrade() -> None:
    # `trip_inquiries` is not rebuilt. It cannot be: the fold that made one chat
    # out of several threads threw away which thread a later message was in, and
    # inventing a thread per message would produce a history nobody had.
    op.drop_index("ix_deals_shipment_no", table_name="deals")
    op.drop_column("deals", "shipment_no")
    op.drop_index("ix_deals_chat_id", table_name="deals")
    op.drop_constraint("fk_deals_chat", "deals", type_="foreignkey")
    op.drop_column("deals", "chat_id")
    op.drop_table("chat_messages")
    op.drop_table("chats")
