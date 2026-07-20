"""T_UX.3 pt.4a — JWT blacklist backed by Redis.

Purpose: give POST /api/auth/logout real teeth. Before pt.4a, logout only
cleared the frontend localStorage; a stolen JWT continued to work until its
30-day natural expiry. Now every revoked `jti` is stored in Redis with a TTL
equal to the token's remaining lifetime — after natural expiry the key
disappears on its own, no cleanup task needed.

Uses `redis>=5.0` asyncio client that already ships with our requirements.
Fails soft: if Redis is unreachable we default to "not blacklisted" and log —
we would rather serve a stale-but-valid JWT than lock everyone out on a
Redis outage. The natural-expiry backstop still applies.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "auth:blacklist:"
_client: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    """Mark a JWT as revoked. TTL should match the remaining lifetime of the
    token — Redis auto-evicts after that, so we never accumulate junk."""
    if ttl_seconds <= 0:
        return
    try:
        await _get_client().set(f"{_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Redis blacklist SET failed for jti=%s: %s", jti, exc)


async def is_blacklisted(jti: str) -> bool:
    """True if the jti was revoked and hasn't expired yet."""
    try:
        return bool(await _get_client().exists(f"{_KEY_PREFIX}{jti}"))
    except Exception as exc:
        logger.warning("Redis blacklist EXISTS failed for jti=%s: %s", jti, exc)
        return False
