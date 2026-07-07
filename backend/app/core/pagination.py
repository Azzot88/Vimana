"""Cursor-based pagination helper.

Cursor = id (UUID) of the last item in the previous page. Server dereferences
the cursor into its `created_at` value and fetches items strictly before/after
that timestamp (depending on sort direction). Response shape:

    {"items": [...], "next_cursor": "<uuid>" | null}

Advantages over offset: stable under inserts, O(log n) via index on
(created_at, id), and clients don't need to know total count.
"""
import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
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
        subq = (
            select(model.created_at)
            .where(model.id == after_uuid)
            .scalar_subquery()
        )
        stmt = stmt.where(model.created_at < subq)
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
        subq = (
            select(model.created_at)
            .where(model.id == after_uuid)
            .scalar_subquery()
        )
        stmt = stmt.where(model.created_at > subq)
    stmt = stmt.order_by(model.created_at.asc(), model.id.asc()).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None
    return items, next_cursor
