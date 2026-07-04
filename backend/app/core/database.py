from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine for Celery tasks (psycopg2)
_sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_engine = create_engine(_sync_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
