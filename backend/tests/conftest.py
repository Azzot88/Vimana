import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.deal import Deal, DealStatus
from app.models.marketplace import Category, DEFAULT_CATEGORIES, Order, OrderStatus, Trip, TripStatus
from app.models.user import User


def _derive_test_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base, _, _ = settings.DATABASE_URL.rpartition("/")
    return f"{base}/vimana_test"


TEST_DATABASE_URL = _derive_test_url()

SEED_CARRIER_EMAIL = "seed-carrier@vimana.test"
SEED_SENDER_EMAIL = "seed-sender@vimana.test"
SEED_PASSWORD = "seed-password-123"


def _ensure_test_database() -> None:
    sync_url = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    _, _, rest = sync_url.partition("://")
    creds, _, host_db = rest.partition("@")
    user, _, password = creds.partition(":")
    host_port, _, dbname = host_db.partition("/")
    host, _, port = host_port.partition(":")
    port = port or "5432"

    conn = psycopg2.connect(
        dbname="postgres", user=user, password=password, host=host, port=port
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{dbname}"')
    cur.close()
    conn.close()


async def _seed_default_categories(engine) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        result = await db.execute(select(Category))
        existing = {c.name_key for c in result.scalars().all()}
        for key in DEFAULT_CATEGORIES:
            if key in existing:
                continue
            db.add(Category(name_key=key, is_default=True, usage_count=0))
        await db.commit()


async def _migrate_orders_category_to_string(engine) -> None:
    """T1.17 schema fix: orders.category enum → VARCHAR(50). Idempotent."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='orders' AND column_name='category'"
                )
            )
        ).fetchone()
        if row and row[0] == "USER-DEFINED":
            await conn.execute(
                text(
                    "ALTER TABLE orders ALTER COLUMN category TYPE VARCHAR(50) USING category::text"
                )
            )
            await conn.execute(text("DROP TYPE IF EXISTS ordercategory"))


async def _ensure_connections_unique(engine) -> None:
    """T1.19 schema fix: UNIQUE(user_id, connected_user_id) on connections. Idempotent."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint "
                    "WHERE conname = 'uq_connections_user_connected'"
                )
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "DELETE FROM connections a USING connections b "
                    "WHERE a.id > b.id AND a.user_id = b.user_id "
                    "AND a.connected_user_id = b.connected_user_id"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE connections ADD CONSTRAINT uq_connections_user_connected "
                    "UNIQUE (user_id, connected_user_id)"
                )
            )


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    _ensure_test_database()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_orders_category_to_string(engine)
    await _ensure_connections_unique(engine)
    await _seed_default_categories(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_maker(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def override_db(session_maker):
    async def _get_test_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _mute_celery(monkeypatch):
    from app.api import deals as deals_module

    class _NoopTask:
        def delay(self, *args, **kwargs):
            return None

    monkeypatch.setattr(deals_module, "notify_deal_status", _NoopTask())


async def _get_or_create_user(db: AsyncSession, *, email: str, display_name: str, is_carrier: bool) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(
        email=email,
        password_hash=hash_password(SEED_PASSWORD),
        display_name=display_name,
        is_carrier=is_carrier,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(scope="session")
async def seed_carrier(session_maker) -> User:
    async with session_maker() as db:
        return await _get_or_create_user(
            db, email=SEED_CARRIER_EMAIL, display_name="Seed Carrier", is_carrier=True
        )


@pytest_asyncio.fixture(scope="session")
async def seed_sender(session_maker) -> User:
    async with session_maker() as db:
        return await _get_or_create_user(
            db, email=SEED_SENDER_EMAIL, display_name="Seed Sender", is_carrier=False
        )


@pytest_asyncio.fixture(scope="session")
async def seed_trip(session_maker, seed_carrier) -> Trip:
    async with session_maker() as db:
        result = await db.execute(
            select(Trip).where(
                Trip.carrier_id == seed_carrier.id,
                Trip.origin == "SEED-ORIGIN",
                Trip.destination == "SEED-DEST",
            )
        )
        trip = result.scalars().first()
        if trip:
            return trip
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="SEED-ORIGIN",
            destination="SEED-DEST",
            depart_at=datetime.now(timezone.utc) + timedelta(days=7),
            capacity=5.0,
            allowed_categories=["document"],
            status=TripStatus.open,
        )
        db.add(trip)
        await db.commit()
        await db.refresh(trip)
        return trip


@pytest_asyncio.fixture(scope="session")
async def seed_deal(session_maker, seed_carrier, seed_sender, seed_trip) -> Deal:
    async with session_maker() as db:
        result = await db.execute(
            select(Deal).where(
                Deal.trip_id == seed_trip.id,
                Deal.sender_id == seed_sender.id,
            )
        )
        deal = result.scalars().first()
        if deal:
            return deal
        order = Order(
            sender_id=seed_sender.id,
            recipient_contact="+10000000000",
            origin=seed_trip.origin,
            destination=seed_trip.destination,
            category="document",
            declared_value=100.0,
            currency="USD",
            description="Seed order",
            status=OrderStatus.matched,
            trip_id=seed_trip.id,
        )
        db.add(order)
        await db.flush()
        deal = Deal(
            order_id=order.id,
            trip_id=seed_trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.matched,
        )
        db.add(deal)
        await db.commit()
        await db.refresh(deal)
        return deal


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def carrier_headers(client, seed_carrier) -> dict[str, str]:
    token = await _login(client, seed_carrier.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sender_headers(client, seed_sender) -> dict[str, str]:
    token = await _login(client, seed_sender.email)
    return {"Authorization": f"Bearer {token}"}


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@vimana.test"
