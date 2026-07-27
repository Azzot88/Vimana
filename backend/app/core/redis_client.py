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

# Keyed by the loop **object**, not `id(loop)`. An address is reused once its
# loop is collected, so an id-keyed cache hands a new loop the client belonging
# to a dead one: calls on it fail, and closing it closes nothing, which leaves
# its connections to be finalised after their loop is gone. Over a few hundred
# short-lived loops that happens constantly. Dict keys hold the loop alive, so
# closed ones are evicted on every lookup.
_clients: dict[asyncio.AbstractEventLoop, aioredis.Redis] = {}


def get_client() -> aioredis.Redis:
    loop = asyncio.get_running_loop()
    # Forget clients whose loop died. They cannot be closed from here —
    # `aclose()` is a coroutine and their loop is gone — so anything that
    # creates short-lived loops should call `aclose_current()` on the way out.
    for cached_loop in [k for k in _clients if k.is_closed()]:
        _clients.pop(cached_loop, None)

    client = _clients.get(loop)
    if client is None:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        _clients[loop] = client
    return client


async def aclose_current() -> None:
    """Close and forget the client bound to the running loop.

    Call this before tearing a loop down. Skipping it is not a correctness bug —
    the socket goes when the process does — but the finalizer noise it produces
    buries real warnings.
    """
    loop = asyncio.get_running_loop()
    client = _clients.pop(loop, None)
    if client is None:
        return

    # `aclose()` alone: `from_url` owns the pool it created, so closing the
    # client tears it down. An explicit `pool.disconnect()` used to sit here,
    # added while chasing finalizer warnings whose real cause was elsewhere —
    # the teardown fixture ran in the wrong event loop and closed nothing at
    # all. Removed once that was fixed and the suite stayed clean without it.
    closer = getattr(client, "aclose", None) or getattr(client, "close", None)
    if closer is not None:
        try:
            await closer()
        except Exception as exc:  # a dead connection is still a closed one
            logger.debug("Redis client close failed: %s", exc)
