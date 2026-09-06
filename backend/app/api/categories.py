from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.marketplace import Category

router = APIRouter()


class CategoryOut(BaseModel):
    name_key: str
    is_default: bool
    usage_count: int
    # T3.11.07 — the picker shows the first few and hides the rest behind
    # "more", so it has to know the order the server decided rather than
    # re-deriving one of its own.
    sort_order: int = 100


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    q: str = Query("", max_length=50),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Category)
    q_norm = q.strip().lower()
    if q_norm:
        stmt = stmt.where(Category.name_key.ilike(f"%{q_norm}%"))
    # T3.11.07 — `usage_count` first, `sort_order` second. This platform's own
    # traffic is the better signal and outranks the seed the moment it exists;
    # the seed (taken from the market analysis) decides only the cold start,
    # when every count is still zero and the fallback would otherwise be
    # alphabetical — which is an order about spelling, not about cargo.
    stmt = stmt.order_by(
        desc(Category.is_default),
        desc(Category.usage_count),
        Category.sort_order,
        Category.name_key,
    ).limit(15)
    result = await db.execute(stmt)
    return [
        CategoryOut(
            name_key=c.name_key,
            is_default=c.is_default,
            usage_count=c.usage_count,
            sort_order=c.sort_order,
        )
        for c in result.scalars().all()
    ]
