"""Shared asyncio-Redis client, cached per event loop.

An asyncio Redis client binds to the loop that created it. A plain module-level
singleton therefore works right up until a second loop touches it, and then
every call raises `RuntimeError: Event loop is closed`. A server has one loop
and never notices; pytest-asyncio builds a fresh loop per test and notices
immediately — and worse, the connections it leaves behind raise inside their own
`__del__` once their loop is gone, which surfaces as a wall of
`PytestUnraisableExceptionWarning`.

This module owns the pattern once so each new consumer cannot re-introduce it.
Both `token_blacklist` and `challenge` had their own copy; the second one was
written knowing about the first and still had to be fixed twice.
"""
from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_clients: dict[int, tuple[asyncio.AbstractEventLoop, aioredis.Redis]] = {}


def get_client() -> aioredis.Redis:
    loop = asyncio.get_running_loop()
    # Forget clients whose loop died. They cannot be closed from here —
    # `aclose()` is a coroutine and their loop is gone — so anything that
    # creates short-lived loops should call `aclose_current()` on the way out.
    for key, (cached_loop, _client) in list(_clients.items()):
        if cached_loop.is_closed():
            _clients.pop(key, None)

    entry = _clients.get(id(loop))
    if entry is None:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        _clients[id(loop)] = (loop, client)
        return client
    return entry[1]


async def aclose_current() -> None:
    """Close and forget the client bound to the running loop.

    Call this before tearing a loop down. Skipping it is not a correctness bug —
    the socket goes when the process does — but the finalizer noise it produces
    buries real warnings.
    """
    loop = asyncio.get_running_loop()
    entry = _clients.pop(id(loop), None)
    if entry is None:
        return
    client = entry[1]
    closer = getattr(client, "aclose", None) or getattr(client, "close", None)
    if closer is None:
        return
    try:
        await closer()
    except Exception as exc:  # a dead connection is still a closed connection
        logger.debug("Redis client close failed: %s", exc)
