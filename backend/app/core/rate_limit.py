import os

from slowapi import Limiter

from app.core.client_ip import client_ip
from app.core.config import settings


def _key_func(request):
    """T_SEC.6 — key on the address nginx observed, not the one the caller sent.

    This read the **leftmost** element of `X-Forwarded-For` until 2026-08-11.
    That element is whatever the caller wrote: sending
    `X-Forwarded-For: <random>` with every request put each one in its own
    bucket, and every limit below — five codes an hour, ten Nostr attempts a
    minute — was one header away from not existing. nginx's `limit_req` zones
    key on `$binary_remote_addr` and so were never fooled, which is the only
    reason this was a hole rather than an open door.
    """
    return client_ip(request)


# Disabled during tests to avoid noisy interactions with pytest sequences.
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

# Counters live in Redis, not in process memory (T_PERF.1).
#
# In memory they reset on every deploy — and a deploy is exactly when someone
# probing `/api/auth/email/request-code` gets their budget handed back. They are
# also per-process, so the limits stop meaning what they say the moment a second
# worker exists. nginx has its own `limit_req` zones (ENVIRONMENT §5.1), but they
# are coarse per-IP zones; the per-endpoint budgets (5/hour for a verification
# code, 10/minute for Nostr auth) exist only here.
#
# `swallow_errors=True` is the deliberate half of this: if Redis is unreachable
# the request passes instead of failing. That matches `D-REVOCATION-IS-BEST-EFFORT`
# — ordinary traffic prefers availability — and nginx still stands in front.
# Step-up stays fail-closed; irreversible actions are the other case.
#
# The storage client is synchronous, so a limited endpoint pays one small
# blocking Redis round trip. Accepted knowingly: it is a sub-millisecond INCR
# over the compose network on low-volume endpoints, unlike the R2 uploads pt.2
# moved off the loop. If it ever shows up in latency, the answer is the async
# storage backend, not a return to in-memory counters.
limiter = Limiter(
    key_func=_key_func,
    enabled=RATE_LIMIT_ENABLED,
    storage_uri=settings.REDIS_URL,
    swallow_errors=True,
)
