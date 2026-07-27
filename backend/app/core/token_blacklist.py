"""T_UX.3 pt.4a — JWT blacklist backed by Redis.

Purpose: give POST /api/auth/logout real teeth. Before pt.4a, logout only
cleared the frontend localStorage; a stolen JWT continued to work until its
30-day natural expiry. Now every revoked `jti` is stored in Redis with a TTL
equal to the token's remaining lifetime — after natural expiry the key
disappears on its own, no cleanup task needed.

Client comes from `core.redis_client`, cached per event loop. It used to be a
module-level singleton, which bound it to whichever loop touched it first; under
pytest-asyncio every subsequent test hit "Event loop is closed", the fail-soft
branch below swallowed it, and revocation silently did nothing for the whole
suite — tests about logout were passing without exercising the mechanism.

Fails soft: if Redis is unreachable we default to "not blacklisted" and log —
we would rather serve a stale-but-valid JWT than lock everyone out on a
Redis outage. The natural-expiry backstop still applies.
"""
from __future__ import annotations

import logging

from app.core.redis_client import get_client as _get_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "auth:blacklist:"


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
