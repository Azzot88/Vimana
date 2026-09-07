"""T3.11.23 — finding the one chat two people have.

Owner's model, 2026-09-07: a chat exists in a single copy per person. The pair
is stored ordered — low uuid first — so `(A, B)` and `(B, A)` are one row, and
the unique index makes that a fact of the database rather than a rule every
caller has to remember. This module is where the ordering lives, once.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketplace import Chat


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """The two ids, low first. The single place that decides what «the pair»
    means — the `CHECK` on the table enforces the same order."""
    return (a, b) if a < b else (b, a)


def chat_participants(chat: Chat) -> tuple[uuid.UUID, uuid.UUID]:
    """Both sides. Roles are deliberately absent from `Chat`: today one of them
    sends and the other carries, tomorrow the other way round, and a chat that
    baked the roles in would need a second row for the same two people."""
    return (chat.user_low_id, chat.user_high_id)


async def chat_for_pair(
    db: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> Chat:
    """The chat these two have, created if this is the first time.

    Idempotent, and idempotent under a race: two requests arriving together both
    find nothing, both insert, and one loses on the unique index. The loser
    re-reads rather than failing — the row it wanted exists, which is the whole
    point of asking.

    Called by: `api.inquiries.open_inquiry`, `api.deals.match_deal`.
    """
    if a == b:
        raise ValueError("a chat needs two different people")
    low, high = ordered_pair(a, b)
    found = (
        await db.execute(
            select(Chat).where(Chat.user_low_id == low, Chat.user_high_id == high)
        )
    ).scalar_one_or_none()
    if found:
        return found

    chat = Chat(user_low_id=low, user_high_id=high)
    db.add(chat)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return (
            await db.execute(
                select(Chat).where(Chat.user_low_id == low, Chat.user_high_id == high)
            )
        ).scalar_one()
    return chat
