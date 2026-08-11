"""T3.29 — how often a code may be *asked for*, per mailbox and per source.

Everything already in place counts requests: slowapi budgets each endpoint per
address (`core/rate_limit`), nginx holds coarse `limit_req` zones in front, and
`contact_verification` refuses a second code for the same value inside sixty
seconds. None of them counts the thing that actually matters here — **how many
different people's mailboxes one caller is writing to.** Ten requests an hour is
a reasonable budget for a person who mistyped their address; the same ten spread
over ten strangers is our form being used as a mailer, and every existing limit
passes it.

Two counters, because the abuse has two shapes:

- **per identifier** — a mailbox that is not ours should not be reachable
  through this form more than a handful of times an hour, no matter how many
  addresses the requests arrive from. The sixty-second cooldown does not bound
  this: it bounds the gap, not the total.
- **identifiers per source** — one caller may ask about a few addresses in an
  hour (a typo, a second account, a household). It may not ask about twenty.

**Redis down means the request passes.** The same trade the rate limiter makes
deliberately (`swallow_errors=True`): ordinary traffic prefers availability, and
nginx's zones are still standing in front. A limiter that turns an outage of its
own storage into a locked front door is a worse failure than the one it prevents.

Functions (PROJECT §6.2a):
- `check(request, identifier)` — raises 429 if either counter is exhausted.
  Called by: `api/auth.otp_request`, `api/auth.request_contact_code`,
  `api/auth.forgot_password`.
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException

from app.core.client_ip import client_ip

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 3600

# Codes an hour to any one mailbox. Above a couple, somebody is either stuck or
# not the owner; the letters themselves say what to do when stuck.
PER_IDENTIFIER = 5

# Distinct mailboxes an hour from one address. Deliberately loose rather than
# tight: mobile carriers put whole cities behind one address (CGNAT), and a
# limit that treats a shared exit as one person locks out the very corridor this
# product serves. Ten still ends bulk use of the form, which is the point — the
# per-identifier counter above is the one doing the protecting per mailbox.
IDENTIFIERS_PER_IP = 10


def _digest(identifier: str) -> str:
    """Key on a hash, not on the address itself.

    Redis holds these keys for an hour and is not the place a list of every
    address anyone typed into the sign-in form should accumulate.
    """
    return hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()[:32]


async def check(request, identifier: str) -> None:
    """Count this request; raise 429 if either budget is spent."""
    if not identifier or not identifier.strip():
        return

    from app.core import rate_limit

    # Off under `RATE_LIMIT_ENABLED=false`, exactly like slowapi's budgets: a
    # suite that sends dozens of codes to the same fixture address would
    # otherwise exhaust an hour's budget in its first minute and fail tests
    # about something else entirely. The tests for *this* module switch it back
    # on explicitly, so both branches actually run — `T_TEST.7` is the record of
    # what a permanently-off branch is worth.
    if not rate_limit.RATE_LIMIT_ENABLED:
        return

    from app.core.redis_client import get_client

    try:
        redis = get_client()
        ip = client_ip(request)

        per_value = f"codelimit:value:{_digest(identifier)}"
        count = await redis.incr(per_value)
        if count == 1:
            # Expiry set on creation, so the window rolls from the first
            # request rather than snapping to a wall-clock hour — a fixed
            # bucket lets twice the budget through across its boundary.
            await redis.expire(per_value, WINDOW_SECONDS)

        per_ip = f"codelimit:ip:{ip}"
        spread = await redis.scard(per_ip)
        # Checked before adding: an identifier already in the set is not a new
        # mailbox, and a caller retrying their own address must not be pushed
        # over the edge by their own retries.
        if spread >= IDENTIFIERS_PER_IP:
            members = await redis.sismember(per_ip, _digest(identifier))
            if not members:
                raise HTTPException(
                    status_code=429, detail="Too many code requests from here"
                )
        else:
            await redis.sadd(per_ip, _digest(identifier))
            if spread == 0:
                await redis.expire(per_ip, WINDOW_SECONDS)

        if count > PER_IDENTIFIER:
            raise HTTPException(
                status_code=429, detail="Too many code requests for this contact"
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("code limit check failed; letting the request through")
