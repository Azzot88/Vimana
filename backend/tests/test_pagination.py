"""Cursor pagination over rows that share a timestamp.

Found the hard way: `test_dealvault.py::test_create_message_appends` counted the
seed deal's vault twice around a single insert and saw it grow by four. Not a
flaky assertion — walking the pages returned a different number of messages
depending on where the boundaries happened to land.

The cause was a mismatch between how rows were ordered and how the cursor was
compared. Ordering used `(created_at, id)`; the cursor filtered on `created_at`
alone. Any group of rows sharing a timestamp that straddled a page boundary lost
its tail. Ties are routine — messages written in one request, seed data inserted
in one transaction — so this was losing real messages from real chats, quietly,
for as long as the helper has existed.

These tests build the tie deliberately instead of hoping the seed data produces
one.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.pagination import paginate_asc, paginate_desc
from app.models.deal import DealVaultMessage

TIED = datetime(2020, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture(loop_scope="function")
async def tied_messages(session_maker, seed_deal):
    """Five messages on one timestamp, framed by one before and one after.

    A dedicated timestamp far in the past keeps them clear of everything else in
    the shared vault, so the assertions are about the tie and nothing else.

    `loop_scope="function"` because `pytest.ini` sets
    `asyncio_default_fixture_loop_scope = session`: without it this fixture
    would open its connections on the session loop while the test body runs on
    the function loop, which is the same mismatch that once made a Redis
    teardown quietly close nothing (see `conftest._close_redis_clients`).

    These rows are cleaned up, unlike the seed data — they exist to make a tie,
    and leaving thousands of them behind across runs would eventually make the
    vault tests slow for no benefit.
    """
    ids: list[uuid.UUID] = []
    async with session_maker() as db:
        for offset in (-1, 0, 0, 0, 0, 0, 1):
            msg = DealVaultMessage(
                id=uuid.uuid4(),
                deal_id=seed_deal.id,
                sender_id=None,
                is_system=True,
                created_at=TIED + timedelta(seconds=offset),
            )
            db.add(msg)
            ids.append(msg.id)
        await db.commit()

    yield ids

    async with session_maker() as db:
        for row_id in ids:
            row = await db.get(DealVaultMessage, row_id)
            if row is not None:
                await db.delete(row)
        await db.commit()


def _window(deal_id):
    """Only the rows this test made — the seed vault holds thousands."""
    return select(DealVaultMessage).where(
        DealVaultMessage.deal_id == deal_id,
        DealVaultMessage.created_at >= TIED - timedelta(seconds=2),
        DealVaultMessage.created_at <= TIED + timedelta(seconds=2),
    )


async def _walk(db, direction, deal_id, limit: int) -> list[uuid.UUID]:
    seen: list[uuid.UUID] = []
    cursor = None
    for _ in range(50):
        items, cursor = await direction(db, _window(deal_id), DealVaultMessage, cursor, limit)
        seen.extend(m.id for m in items)
        if not cursor:
            break
    return seen


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 6])
async def test_ascending_walk_returns_every_row(
    session_maker, seed_deal, tied_messages, limit
):
    """Every page size must yield all seven rows, once each.

    Parametrised because the bug only bit when a boundary fell *inside* the tied
    group — a single limit would have passed while the code was still broken.
    """
    async with session_maker() as db:
        seen = await _walk(db, paginate_asc, seed_deal.id, limit)

    assert len(seen) == len(tied_messages), f"limit={limit} lost or repeated rows"
    assert set(seen) == set(tied_messages)
    assert len(set(seen)) == len(seen), "a row came back on two pages"


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 6])
async def test_descending_walk_returns_every_row(
    session_maker, seed_deal, tied_messages, limit
):
    async with session_maker() as db:
        seen = await _walk(db, paginate_desc, seed_deal.id, limit)

    assert len(seen) == len(tied_messages), f"limit={limit} lost or repeated rows"
    assert set(seen) == set(tied_messages)


async def test_walking_twice_agrees(session_maker, seed_deal, tied_messages):
    """The count must not depend on where the boundaries land — that instability
    is what the failing vault test actually observed."""
    async with session_maker() as db:
        assert len(await _walk(db, paginate_asc, seed_deal.id, 2)) == len(
            await _walk(db, paginate_asc, seed_deal.id, 3)
        )


async def test_ascending_order_is_stable_across_the_tie(
    session_maker, seed_deal, tied_messages
):
    """Ties break by id, and paging must follow the same rule the ordering does
    — otherwise a row can be both 'already seen' and 'not yet reached'."""
    async with session_maker() as db:
        one_page = await _walk(db, paginate_asc, seed_deal.id, 50)
        paged = await _walk(db, paginate_asc, seed_deal.id, 2)

    assert paged == one_page


async def test_unknown_cursor_yields_nothing(session_maker, seed_deal):
    """A cursor naming a row that no longer exists must not silently restart
    from the beginning and replay the whole list."""
    async with session_maker() as db:
        items, cursor = await paginate_asc(
            db, _window(seed_deal.id), DealVaultMessage, str(uuid.uuid4()), 10
        )
    assert items == []
    assert cursor is None


async def test_malformed_cursor_is_not_an_error(session_maker, seed_deal):
    async with session_maker() as db:
        items, cursor = await paginate_asc(
            db, _window(seed_deal.id), DealVaultMessage, "not-a-uuid", 10
        )
    assert items == []
    assert cursor is None
