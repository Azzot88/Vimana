import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_func(request):
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or get_remote_address(request)
    )


# Disabled during tests to avoid noisy interactions with pytest sequences.
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

limiter = Limiter(key_func=_key_func, enabled=RATE_LIMIT_ENABLED)
