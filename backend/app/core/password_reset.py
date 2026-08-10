"""T_SEC.5 — the way back for an account that has a password and forgot it.

Before this the only recovery was a set of codes created on purpose through a
step-up ceremony nobody is pushed towards, so the ordinary case — registered
with an email and a password, forgot the password — had no path at all. The
login screen offered to accept a recovery code the person had never made, which
reads as "you did something wrong" for a situation the product created.

Design, and the reasons that are not obvious:

**A long random token, not a six-digit code.** The email confirmation code is
short because it is typed by someone who already holds the session; this one
arrives at a mailbox and hands over the account. Brute force against six digits
is minutes; against 32 bytes it is not a consideration, and there is nothing to
type — the link carries it.

**Only a verified address.** An unverified one is an address somebody typed,
not a mailbox anybody proved they read. Sending an account-recovery link there
would let anyone who can register with your address take the account. This is
the first place in the product where verification actually gates something, and
it gates the one thing it should.

**Stored hashed.** A live token readable out of a backup is a takeover kit for
every reset in flight.

**One hour.** Long enough for a mail queue and a person who reads mail on their
phone later; short enough that a link forwarded or left in a mailbox stops
being a key by the evening.

Functions (PROJECT §6.2a):
- `issue_token(user)` — mints, stores the hash, returns the plaintext.
  Called by: `api/auth.forgot_password`.
- `consume_token(user, token)` — verifies, clears, raises on failure.
  Called by: `api/auth.reset_password`.
- `reset_target(user)` — the address a link may be sent to, or None.
  Called by: `api/auth.forgot_password`, `tasks/notifications.send_password_reset`.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password, verify_password
from app.models.user import User

TOKEN_TTL = timedelta(hours=1)


class ResetError(RuntimeError):
    """Base for every refusal below."""


class ResetInvalid(ResetError):
    """No pending reset, or the token does not match."""


class ResetExpired(ResetError):
    """The window closed."""


def reset_target(user: User) -> str | None:
    """Where a reset link may go for this account.

    `None` for an account with no address, and for one whose address is not
    confirmed. The caller must not fall back to anything else: there is no
    second-best mailbox for handing over an account.
    """
    if not user.email or user.email_verified_at is None:
        return None
    return user.email


def issue_token(user: User, *, now: datetime | None = None) -> str:
    """Mint a reset token, store only its hash, return the plaintext once."""
    moment = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    user.password_reset_hash = hash_password(token)
    user.password_reset_expires_at = moment + TOKEN_TTL
    return token


def consume_token(user: User, token: str, *, now: datetime | None = None) -> None:
    """Verify and burn. Raises rather than returning a bool.

    Burning happens on success only. A wrong guess must not invalidate the real
    token still sitting in the owner's mailbox — otherwise anyone who can reach
    the reset endpoint can deny the account its recovery by guessing once.
    """
    moment = now or datetime.now(timezone.utc)
    if not user.password_reset_hash or not user.password_reset_expires_at:
        raise ResetInvalid("no reset pending")

    expires = user.password_reset_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= moment:
        clear_token(user)
        raise ResetExpired("reset token expired")

    if not verify_password(token, user.password_reset_hash):
        raise ResetInvalid("reset token does not match")

    clear_token(user)


def clear_token(user: User) -> None:
    user.password_reset_hash = None
    user.password_reset_expires_at = None
