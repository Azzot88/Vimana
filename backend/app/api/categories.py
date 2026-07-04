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


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    q: str = Query("", max_length=50),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Category)
    q_norm = q.strip().lower()
    if q_norm:
        stmt = stmt.where(Category.name_key.ilike(f"%{q_norm}%"))
    stmt = stmt.order_by(desc(Category.is_default), desc(Category.usage_count), Category.name_key).limit(15)
    result = await db.execute(stmt)
    return [
        CategoryOut(name_key=c.name_key, is_default=c.is_default, usage_count=c.usage_count)
        for c in result.scalars().all()
    ]
