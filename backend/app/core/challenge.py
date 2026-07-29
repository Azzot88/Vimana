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

import logging
import secrets

from app.core.redis_client import get_client as _get_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "challenge:"
CHALLENGE_TTL_SECONDS = 300


class ChallengeUnavailable(RuntimeError):
    """Redis is unreachable — refuse rather than guess."""


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


async def store_challenge(scope: str, subject: str, value: str) -> None:
    """Store a challenge we did **not** generate.

    WebAuthn (T3.14) mints its own challenge inside the options object, so
    `issue_challenge` does not fit: we have to keep what the library produced,
    not hand out our own nonce.
    """
    try:
        await _get_client().set(_key(scope, subject), value, ex=CHALLENGE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Redis challenge SET failed (%s/%s): %s", scope, subject, exc)
        raise ChallengeUnavailable() from exc


async def take_challenge(scope: str, subject: str) -> str | None:
    """Burn the stored challenge and return it.

    For flows where the client does not echo the challenge back as a separate
    field — WebAuthn buries it inside `clientDataJSON`, and the library needs
    the expected value to compare against. Burning on read keeps the one-shot
    property: a replay finds nothing.
    """
    try:
        return await _get_client().getdel(_key(scope, subject))
    except Exception as exc:
        logger.warning("Redis challenge GETDEL failed (%s/%s): %s", scope, subject, exc)
        raise ChallengeUnavailable() from exc


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
