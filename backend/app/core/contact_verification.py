"""T3.25 — one code lifecycle for every channel.

The mechanics are not new: TTL, five attempts, a sixty-second cooldown, the
code stored hashed, and exhaustion burning the code rather than merely refusing
the attempt. All of it was written for email in T3.11 and has run since. What is
new is that it no longer lives on `users` columns, so the second, third and
fourth channel reuse it instead of forking it.

Named `contact_verification`, not `verification`: `core/verification.py` is
T2.1's peer-verification module — document containers and badge levels — and
the two have nothing in common but the word.

Two decisions carried over deliberately, because both look like bugs until the
reason is stated:

**Running out of attempts destroys the code**, it does not merely reject the
try. A code that survives its own attempt limit invites waiting for the counter
to be forgotten; burning it costs the honest user one more message and costs the
attacker the whole guess.

**The cooldown is per value, not per account.** At sign-up there is no account
yet — that is exactly why `user_id` is nullable — so an account-based limit
would protect only the paths that already have a session.

> **No callers yet, and that is deliberate.** This is the foundation `T3.26`
> (channel abstraction) and `T3.28` (one-field sign-in) are built on, and they
> are next in the queue. Said aloud per PROJECT §6.2a and listed in TECHSTATE
> §3a so it cannot become a silent tail if the queue changes. Email
> confirmation keeps running on the T3.11 column path until `T3.26` moves it
> here — one storage swap, made when the second channel makes it necessary,
> rather than two mechanisms living side by side in the meantime.

Functions (PROJECT §6.2a):
- `issue(db, channel, value, purpose, user_id)` — mint a code, store its hash,
  return the plaintext. Called by: `T3.26`, `T3.28`.
- `verify(db, channel, value, code, purpose)` — check and consume.
  Called by: `T3.26`, `T3.28`.
- `generate_code()` — six digits from `secrets`. Called by: `issue`, tests.
- `_active(db, channel, value, purpose)` — the live challenge, if any.
  Called by: `issue`, `verify`.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.contact import VerificationChallenge

CODE_TTL = timedelta(minutes=15)
COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


class VerificationError(RuntimeError):
    """Base for every refusal below."""


class CooldownActive(VerificationError):
    """A code was sent moments ago; asking again does not send another."""


class NoCodeIssued(VerificationError):
    """Nothing is pending for this channel and value."""


class CodeExpired(VerificationError):
    """The window closed."""


class CodeInvalid(VerificationError):
    """Wrong code; the attempt is counted."""


class TooManyAttempts(VerificationError):
    """The limit was reached and the code is gone."""


def generate_code() -> str:
    """Six digits, uniformly.

    `secrets.randbelow`, not `random.randint`: the latter draws from a PRNG
    seeded predictably, and this number is the only thing standing between a
    stranger and an address.
    """
    return f"{secrets.randbelow(10**6):06d}"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _active(
    db: AsyncSession, channel: str, value: str, purpose: str
) -> VerificationChallenge | None:
    result = await db.execute(
        select(VerificationChallenge)
        .where(
            VerificationChallenge.channel == channel,
            VerificationChallenge.value == value,
            VerificationChallenge.purpose == purpose,
        )
        .order_by(VerificationChallenge.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def issue(
    db: AsyncSession,
    channel: str,
    value: str,
    *,
    purpose: str = "verify",
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> str:
    """Mint a code for this channel and value. Returns the plaintext once.

    Replaces any earlier challenge for the same target: two live codes for one
    address means the older one is a second key nobody remembers issuing.
    """
    moment = now or datetime.now(timezone.utc)

    existing = await _active(db, channel, value, purpose)
    if existing:
        sent = _aware(existing.sent_at)
        if sent and moment - sent < COOLDOWN:
            raise CooldownActive("a code was sent moments ago")
        await db.execute(
            delete(VerificationChallenge).where(VerificationChallenge.id == existing.id)
        )

    code = generate_code()
    db.add(
        VerificationChallenge(
            user_id=user_id,
            channel=channel,
            value=value,
            code_hash=hash_password(code),
            purpose=purpose,
            expires_at=moment + CODE_TTL,
            sent_at=moment,
        )
    )
    return code


async def verify(
    db: AsyncSession,
    channel: str,
    value: str,
    code: str,
    *,
    purpose: str = "verify",
    now: datetime | None = None,
) -> VerificationChallenge:
    """Check a code and consume it. Raises on every kind of refusal.

    Returns the challenge so the caller can read `user_id`: at sign-in that is
    the only link between a code and an account, and looking it up separately
    would let the two disagree.
    """
    moment = now or datetime.now(timezone.utc)
    challenge = await _active(db, channel, value, purpose)
    if challenge is None:
        raise NoCodeIssued("nothing pending for this value")

    expires = _aware(challenge.expires_at)
    if expires and expires <= moment:
        await db.execute(
            delete(VerificationChallenge).where(VerificationChallenge.id == challenge.id)
        )
        raise CodeExpired("code expired")

    if not verify_password(code, challenge.code_hash):
        challenge.attempts += 1
        if challenge.attempts >= MAX_ATTEMPTS:
            await db.execute(
                delete(VerificationChallenge).where(
                    VerificationChallenge.id == challenge.id
                )
            )
            raise TooManyAttempts("too many attempts; the code is gone")
        raise CodeInvalid("wrong code")

    await db.execute(
        delete(VerificationChallenge).where(VerificationChallenge.id == challenge.id)
    )
    return challenge
