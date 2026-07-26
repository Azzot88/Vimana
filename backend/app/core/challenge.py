"""T3.12 pt.2 — one-time challenges in Redis.

Used to prove control of a key: the server hands out a nonce, the client signs
it, the server checks the signature and **burns the nonce**. Without the burn a
captured signature replays forever, which is the whole attack this is meant to
stop.

Redis rather than a table: these live for minutes, expire on their own, and a
failed cleanup should not leave rows behind. `GETDEL` makes read-and-burn
atomic, so two concurrent requests cannot both consume the same nonce.

Unlike `token_blacklist`, this does **not** fail soft. A Redis outage there
meant "serve a still-valid JWT"; here it would mean "accept a proof we never
issued". Refusing is the only safe answer.

T3.13 (login by Nostr key) reuses this with a different `scope`.
"""
from __future__ import annotations

import asyncio
import logging
import secrets

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "challenge:"
CHALLENGE_TTL_SECONDS = 300

# Keyed by event loop, not a single module-level client. An asyncio Redis client
# binds to the loop that created it, so a cached one raises "Event loop is
# closed" the moment a second loop uses it. Production has exactly one loop and
# behaves as a plain singleton; pytest-asyncio makes a fresh loop per test and
# would otherwise see every request after the first fail.
_clients: dict[int, tuple[asyncio.AbstractEventLoop, aioredis.Redis]] = {}


class ChallengeUnavailable(RuntimeError):
    """Redis is unreachable — refuse rather than guess."""


def _get_client() -> aioredis.Redis:
    loop = asyncio.get_running_loop()
    # Drop clients whose loop is gone, or a long test session accumulates one
    # idle connection pool per test. The client is not closed explicitly:
    # `aclose()` is a coroutine and its loop is already dead, so there is
    # nothing to await it on — releasing the reference lets GC take the socket.
    for key, (cached_loop, _cached_client) in list(_clients.items()):
        if cached_loop.is_closed():
            _clients.pop(key, None)

    entry = _clients.get(id(loop))
    if entry is None:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        _clients[id(loop)] = (loop, client)
        return client
    return entry[1]


def _key(scope: str, subject: str) -> str:
    return f"{_KEY_PREFIX}{scope}:{subject}"


async def issue_challenge(scope: str, subject: str) -> str:
    """Mint a nonce for (scope, subject). Overwrites any previous one — asking
    for a new challenge invalidates the old, so a user who reloads the page
    cannot be tricked into signing a stale one."""
    nonce = secrets.token_hex(32)
    try:
        await _get_client().set(
            _key(scope, subject), nonce, ex=CHALLENGE_TTL_SECONDS
        )
    except Exception as exc:
        logger.warning("Redis challenge SET failed (%s/%s): %s", scope, subject, exc)
        raise ChallengeUnavailable() from exc
    return nonce


async def consume_challenge(scope: str, subject: str, presented: str) -> bool:
    """Burn the stored nonce and report whether it matched.

    Burns on *any* attempt, right or wrong: leaving a nonce alive after a failed
    guess would let an attacker keep trying against the same one.
    """
    try:
        stored = await _get_client().getdel(_key(scope, subject))
    except Exception as exc:
        logger.warning("Redis challenge GETDEL failed (%s/%s): %s", scope, subject, exc)
        raise ChallengeUnavailable() from exc
    if not stored or not presented:
        return False
    return secrets.compare_digest(stored, presented)
