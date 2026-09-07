"""Cursor-based pagination helper.

Cursor = id (UUID) of the last item in the previous page. The server
dereferences it into that row's `created_at` and continues from the
`(created_at, id)` pair. Response shape:

    {"items": [...], "next_cursor": "<uuid>" | null}

Advantages over offset: stable under inserts, O(log n) via index on
(created_at, id), and clients don't need to know a total count.

**The comparison must use the same key as the ordering.** Rows are ordered by
`(created_at, id)`, so the cursor is compared as a row value, not by timestamp
alone. Comparing `created_at` on its own silently drops rows: with
`A(T1) B(T2) C(T2) D(T3)` and a limit of 2, the first page ends at B, and
`created_at > T2` then skips C entirely. Timestamps tie constantly — messages
written in the same request, seed data inserted in one transaction — so this is
routine, not a corner case. It surfaced as a deal vault whose message count
changed depending on where the page boundaries happened to fall, and in a
product whose whole claim is that the vault is complete, silently losing a
message from a chat is about as bad as a paging bug gets.
"""
import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _cursor_key(model, after_uuid: uuid.UUID):
    """The `(created_at, id)` pair the cursor row sits at.

    `created_at` is looked up rather than carried in the cursor so the cursor
    stays an opaque id — clients cannot forge a position, and the value cannot
    drift from the row it names.
    """
    created_at = (
        select(model.created_at).where(model.id == after_uuid).scalar_subquery()
    )
    return tuple_(created_at, literal(after_uuid, type_=model.id.type))


async def paginate_desc(
    db: AsyncSession,
    base_stmt,
    model,
    after: str | None,
    limit: int,
):
    """Descending pagination by (created_at, id). Newest first."""
    stmt = base_stmt
    if after:
        try:
            after_uuid = uuid.UUID(after)
        except ValueError:
            return [], None
        stmt = stmt.where(
            tuple_(model.created_at, model.id) < _cursor_key(model, after_uuid)
        )
    stmt = stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None
    return items, next_cursor


async def paginate_asc(
    db: AsyncSession,
    base_stmt,
    model,
    after: str | None,
    limit: int,
):
    """Ascending pagination by (created_at, id). Oldest first (chat-style)."""
    stmt = base_stmt
    if after:
        try:
            after_uuid = uuid.UUID(after)
        except ValueError:
            return [], None
        stmt = stmt.where(
            tuple_(model.created_at, model.id) > _cursor_key(model, after_uuid)
        )
    stmt = stmt.order_by(model.created_at.asc(), model.id.asc()).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None
    return items, next_cursor
