"""T3.13 — sign in and sign up with a Nostr key.

No password, no email required: the account *is* the key (`D-KEY-IS-IDENTITY`).
The server hands out a one-time challenge, the client signs it with the key it
claims, and the server checks that signature against the claimed npub. Same
machinery as `establish` (`core/challenge.py` + `core/identity_proof.py`), a
different purpose — and the purpose is inside the signed payload, so a proof
minted to log in cannot be replayed to create an account, or the other way
round.

An account created this way is self-custody from birth: `password_hash` is
NULL, `nsec_encrypted` is NULL, and the platform never had a key it could sign
with on this user's behalf. There is nothing to "establish" later.

Unknown key on login answers **404, not 401**. The distinction is deliberate:
the client needs to tell "this key is not registered — offer signup" apart from
"your signature did not check out". Creating an account silently on any valid
signature would mean every stray signature mints a user.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.challenge import ChallengeUnavailable, consume_challenge, issue_challenge
from app.core.challenge import CHALLENGE_TTL_SECONDS
from app.core.database import get_db
from app.core.email_verification import (
    is_auto_verify_domain,
    is_valid_email,
    normalize_email,
)
from app.core.identity_proof import PURPOSE_LOGIN, PURPOSE_SIGNUP, verify_proof
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import Token, UserOut

router = APIRouter()

_SCOPE = "nostr:auth"


def _hex64(value: str, field: str) -> str:
    v = value.strip().lower()
    if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
        raise ValueError(f"{field} must be 64 lowercase hex chars")
    return v


class ChallengeIn(BaseModel):
    pubkey_hex: str

    @field_validator("pubkey_hex")
    @classmethod
    def _pk(cls, v: str) -> str:
        return _hex64(v, "pubkey_hex")


class ChallengeOut(BaseModel):
    challenge: str
    expires_in: int
    purpose_login: str
    purpose_signup: str


class ProofIn(BaseModel):
    npub_hex: str
    challenge: str
    created_at: int
    sig: str

    @field_validator("npub_hex")
    @classmethod
    def _pk(cls, v: str) -> str:
        return _hex64(v, "npub_hex")

    @field_validator("sig")
    @classmethod
    def _sig(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 128 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("sig must be 128 lowercase hex chars")
        return v


class SignupIn(ProofIn):
    display_name: str
    email: str | None = None
    can_carry: bool = True
    can_send: bool = True
    active_mode: str = "sender"

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("display_name must be 1..100 chars")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        if not is_valid_email(v):
            raise ValueError("Invalid email address")
        return normalize_email(v)

    @field_validator("active_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in ("sender", "carrier"):
            raise ValueError("active_mode must be 'sender' or 'carrier'")
        return v


class SignupOut(BaseModel):
    user: UserOut
    token: Token


@router.post("/challenge", response_model=ChallengeOut)
@limiter.limit("10/minute")
async def nostr_challenge(request: Request, body: ChallengeIn):
    """Anyone may ask for a challenge on any pubkey — it is worthless without
    the matching private key, and refusing unknown pubkeys here would turn this
    into an oracle for which keys have accounts."""
    try:
        nonce = await issue_challenge(_SCOPE, body.pubkey_hex)
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    return ChallengeOut(
        challenge=nonce,
        expires_in=CHALLENGE_TTL_SECONDS,
        purpose_login=PURPOSE_LOGIN,
        purpose_signup=PURPOSE_SIGNUP,
    )


async def _consume_and_verify(body: ProofIn, purpose: str) -> None:
    """Burn the challenge, then check the signature. Raises on failure."""
    try:
        ok = await consume_challenge(_SCOPE, body.npub_hex, body.challenge)
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    if not ok:
        raise HTTPException(status_code=401, detail="Challenge is unknown or used")
    if not verify_proof(
        body.npub_hex, purpose, body.challenge, body.created_at, body.sig
    ):
        raise HTTPException(status_code=401, detail="Invalid proof of key possession")


@router.post("/verify", response_model=Token)
@limiter.limit("10/minute")
async def nostr_verify(
    request: Request, body: ProofIn, db: AsyncSession = Depends(get_db)
):
    await _consume_and_verify(body, PURPOSE_LOGIN)

    result = await db.execute(select(User).where(User.nostr_pubkey == body.npub_hex))
    user = result.scalar_one_or_none()
    if user is None:
        # Not an auth failure — the client should offer signup. An account is
        # never created here: a valid signature proves key ownership, not intent
        # to join.
        raise HTTPException(status_code=404, detail="nostr_pubkey_unknown")
    if user.key_lost_at is not None:
        raise HTTPException(
            status_code=403,
            detail="Identity key was declared lost — this account is retired",
        )

    return Token(access_token=create_access_token(str(user.id)))


@router.post("/signup", response_model=SignupOut, status_code=201)
@limiter.limit("10/minute")
async def nostr_signup(
    request: Request, body: SignupIn, db: AsyncSession = Depends(get_db)
):
    """Bring your own key. This is the **only** way a user-held key enters the
    system — on a live account it can never be swapped (T3.12)."""
    await _consume_and_verify(body, PURPOSE_SIGNUP)

    taken = await db.execute(select(User).where(User.nostr_pubkey == body.npub_hex))
    if taken.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This key already has an account")

    if body.email:
        existing = await db.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="email already registered")

    user = User(
        email=body.email,
        password_hash=None,  # no password path at all — the key is the login
        display_name=body.display_name,
        can_carry=body.can_carry,
        can_send=body.can_send,
        active_mode=body.active_mode,
        nostr_pubkey=body.npub_hex,
        nsec_encrypted=None,
        nsec_nonce=None,
        key_self_custody=True,
    )
    if body.email and is_auto_verify_domain(body.email):
        from datetime import datetime, timezone

        user.email_verified_at = datetime.now(timezone.utc)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Optional email still gets its confirmation code — the address is only
    # useful for recovery and deal notifications if it is actually theirs.
    if user.email and user.email_verified_at is None:
        from app.api.auth import _dispatch_code

        _dispatch_code(user)
        await db.commit()

    # A token, not just the row: there is no password to log in with afterwards.
    return SignupOut(
        user=UserOut.model_validate(user, from_attributes=True),
        token=Token(access_token=create_access_token(str(user.id))),
    )
