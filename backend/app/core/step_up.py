"""T3.15 — proving you are still there, whichever way you signed in.

A session token says "someone logged in as this account at some point". For an
irreversible action that is not enough: the laptop may be unattended, the token
may be stolen. Step-up asks for a fresh proof *now*.

Three proofs, one per way in — password, WebAuthn assertion, Nostr signature —
because an account with no password must not be second-class. That was the
concrete gap this task exists to close: `declare-lost` checked a password and
answered 409 to passwordless accounts, i.e. the users most likely to need it.

**Scoped on purpose.** A grant names the operation it was issued for. Confirming
"unlink this device" must not silently authorise "declare my key lost" — the
user consented to one thing, and a grant that covers both turns a small
confirmation into a blank cheque.

**Fail-closed**, unlike `token_blacklist` (`D-REVOCATION-IS-BEST-EFFORT`).
There, a Redis outage falls back to "not revoked" so an outage does not lock
everyone out — availability wins for ordinary traffic. Here the same reflex
would mean "Redis is down, so skip the confirmation" in front of an action that
cannot be undone. Refusing is the only defensible answer.
"""
from __future__ import annotations

import enum
import logging
import secrets

from fastapi import HTTPException

from app.core.redis_client import get_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "stepup:"
STEP_UP_TTL_SECONDS = 300


class StepUpScope(str, enum.Enum):
    """One value per irreversible or security-relevant operation."""

    DECLARE_LOST = "declare_lost"
    UNLINK_PASSKEY = "unlink_passkey"
    CHANGE_EMAIL = "change_email"
    # Covers setting a first password as well as replacing one. From the user's
    # side it is a single operation, and the confirmation it warrants is the
    # same either way — a separate scope would only make the dialog ask twice
    # for the same thing.
    CHANGE_PASSWORD = "change_password"
    ADD_AUTH_METHOD = "add_auth_method"


def _key(user_id: str, scope: StepUpScope) -> str:
    return f"{_KEY_PREFIX}{scope.value}:{user_id}"


async def grant(user_id: str, scope: StepUpScope) -> str:
    """Issue a step-up token after a proof has been verified.

    Overwrites any previous grant for the same (user, scope): re-confirming
    should replace the earlier window, not stack up a second one.
    """
    token = secrets.token_urlsafe(32)
    try:
        await get_client().set(_key(user_id, scope), token, ex=STEP_UP_TTL_SECONDS)
    except Exception as exc:
        logger.warning("step-up grant failed for %s/%s: %s", user_id, scope, exc)
        raise HTTPException(
            status_code=503, detail="Confirmation service unavailable"
        )
    return token


async def consume(user_id: str, scope: StepUpScope, presented: str | None) -> None:
    """Spend a step-up token, or refuse. Raises `HTTPException` on any failure.

    Single-use: the token is burned on read, so one confirmation authorises one
    action. A grant that survived its use would let a captured token be replayed
    for the rest of its five minutes.
    """
    if not presented:
        raise HTTPException(
            status_code=401,
            detail="This action needs confirmation — obtain a step-up token first",
        )
    try:
        stored = await get_client().getdel(_key(user_id, scope))
    except Exception as exc:
        # Fail closed. See the module docstring: an unavailable confirmation
        # store must not become an absent confirmation.
        logger.warning("step-up consume failed for %s/%s: %s", user_id, scope, exc)
        raise HTTPException(
            status_code=503, detail="Confirmation service unavailable"
        )
    if not stored or not secrets.compare_digest(stored, presented):
        raise HTTPException(status_code=401, detail="Confirmation is invalid or expired")


def available_methods(user, credential_count: int) -> list[str]:
    """Which proofs this account can actually produce.

    The UI needs this to avoid offering a password prompt to an account that
    has no password. Mirrors `core.webauthn.remaining_ways_in`, but returns the
    names rather than the count.
    """
    methods: list[str] = []
    if user.password_hash:
        methods.append("password")
    if credential_count:
        methods.append("passkey")
    if user.key_self_custody and user.key_lost_at is None:
        methods.append("nostr")
    return methods
