"""T3.11 — email ownership proof by 6-digit code.

Design notes:

- The code is stored **hashed** (bcrypt, same helper as passwords). A leaked
  dump must not hand out working codes, and the platform itself cannot read
  back a code it already sent.
- `attempts` is per-issued-code. Hitting the cap burns the code outright
  instead of just refusing the guess — otherwise the cap only slows an attacker
  down, it does not stop them.
- **Verification gates nothing.** Owner's decision, 2026-07-26: an unproven
  address is a security question, not a capability question. It never blocks
  login, publishing a trip, or starting a deal. What it protects is the channel
  itself — account recovery and deal notifications go to that address, and an
  unproven one means we cannot tell whether they reach the right person.
  Surfacing it is the UI's job (banner + code screen), not the API's.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.user import User

CODE_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5

# Deliberately loose: this is a shape check, not an RFC 5322 parser. Real proof
# of the address is the code we are about to send to it — which is the whole
# point of the feature. Avoids pulling in `email-validator` as a dependency.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class VerificationError(RuntimeError):
    """Base for the failure modes below. Mapped to HTTP in `api/auth.py`."""


class CooldownActive(VerificationError):
    pass


class NoCodeIssued(VerificationError):
    pass


class CodeExpired(VerificationError):
    pass


class CodeInvalid(VerificationError):
    pass


class TooManyAttempts(VerificationError):
    pass


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


def is_valid_email(raw: str) -> bool:
    """Shape check for every address this system accepts.

    ASCII is part of the shape, not a nicety. The regex below is happy with
    `\x80@x.test` — nothing there is whitespace or `@` — and such an address
    passed registration, email change, passkey and Nostr signup alike. It then
    reached `smtplib.sendmail`, which encodes the envelope as ASCII and raises
    `UnicodeEncodeError`: a 500 in the request that sent it, or a Celery task
    dying every time anyone wrote to that account.

    Internationalised addresses are real and this refusal is a limitation, not
    a judgement — sending to one needs SMTPUTF8, which this stack does not
    negotiate. Accepting an address we provably cannot write to is worse than
    saying no at the door.

    Found by the contract fuzzer through `POST /admin/email/test` (2026-08-09);
    the first fix validated only that endpoint and missed the five other doors
    into the same column.
    """
    value = normalize_email(raw)
    if not value or len(value) > 255:
        return False
    if not value.isascii():
        return False
    return _EMAIL_RE.match(value) is not None


def _aware(value: datetime | None) -> datetime | None:
    """Treat a naive timestamp as UTC — same convention as `core.deal_chain`."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def auto_verify_domains() -> frozenset[str]:
    raw = settings.E2E_AUTO_VERIFY_EMAIL_DOMAINS or ""
    return frozenset(d.strip().lower() for d in raw.split(",") if d.strip())


def is_auto_verify_domain(email: str | None) -> bool:
    """E2E escape hatch. An empty setting — the production default — disables
    it entirely; see `Settings.E2E_AUTO_VERIFY_EMAIL_DOMAINS`."""
    if not email:
        return False
    domains = auto_verify_domains()
    if not domains:
        return False
    _, _, domain = normalize_email(email).rpartition("@")
    return domain in domains


def target_email(user: User) -> str | None:
    """The address a pending code refers to.

    A change in flight takes precedence: the code was sent there, so that is
    what proving it proves. Without this the same code would appear to confirm
    the *old* address — a code delivered to one mailbox settling a claim about
    another.
    """
    return user.pending_email or user.email


def issue_code(user: User, *, now: datetime | None = None) -> str:
    """Mint a fresh code and stamp it on the user. Returns the plaintext for
    delivery — the caller hands it to the Celery task and drops it.

    Resets `attempts`: a new code is a new budget, otherwise a user who
    fat-fingered five times could never recover without support.
    """
    now = now or datetime.now(timezone.utc)
    sent_at = _aware(user.email_verification_sent_at)
    if sent_at is not None and now - sent_at < RESEND_COOLDOWN:
        raise CooldownActive()

    code = generate_code()
    user.email_verification_code_hash = hash_password(code)
    user.email_verification_expires_at = now + CODE_TTL
    user.email_verification_sent_at = now
    user.email_verification_attempts = 0
    return code


def _clear_code(user: User) -> None:
    user.email_verification_code_hash = None
    user.email_verification_expires_at = None
    user.email_verification_attempts = 0


def verify_code(user: User, code: str, *, now: datetime | None = None) -> None:
    """Consume a code. Raises on every failure path; returns None on success.

    Success clears the code state — a verified address has no pending code, and
    leaving the hash around would let a replay land after a later re-issue.
    """
    now = now or datetime.now(timezone.utc)

    if not user.email_verification_code_hash:
        raise NoCodeIssued()

    expires_at = _aware(user.email_verification_expires_at)
    if expires_at is None or now >= expires_at:
        _clear_code(user)
        raise CodeExpired()

    if user.email_verification_attempts >= MAX_ATTEMPTS:
        _clear_code(user)
        raise TooManyAttempts()

    if not verify_password(code.strip(), user.email_verification_code_hash):
        user.email_verification_attempts += 1
        if user.email_verification_attempts >= MAX_ATTEMPTS:
            _clear_code(user)
            raise TooManyAttempts()
        raise CodeInvalid()

    # A pending change lands here and nowhere else: the proof and the swap are
    # the same event. Splitting them across caller and helper is how one of the
    # two eventually gets forgotten on a new code path.
    #
    # The caller must flush and be ready for an IntegrityError — `email` is
    # unique, and the address may have been taken while this change was in
    # flight. Nothing is reserved for a pending claim by design.
    if user.pending_email:
        user.email = user.pending_email
        user.pending_email = None

    user.email_verified_at = now
    _clear_code(user)
