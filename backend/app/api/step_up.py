"""T3.15 — step-up endpoints: prove you are still here, then act.

Two calls. `options` says which proofs this account can produce and hands out a
challenge for the signature-based ones. `verify` takes exactly one proof and
returns a short-lived, single-use token scoped to one operation.

Why not simply re-check the password inline at each sensitive endpoint: because
a growing share of accounts have no password at all (T3.13/T3.14), and the one
irreversible action they most need — declaring a key lost — was refusing them
outright. Step-up exists so "how did you sign in" stops deciding "what may you
confirm".

No `from __future__ import annotations` here: with slowapi's `@limiter.limit`
it turns Pydantic bodies into query params (see `nostr_auth.py`).
"""

import json
import secrets
import time

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.api.deps import get_current_user
from app.core.challenge import (
    CHALLENGE_TTL_SECONDS,
    ChallengeUnavailable,
    store_challenge,
    take_challenge,
)
from app.core.database import get_db
from app.core.identity_proof import step_up_purpose, verify_proof
from app.core.rate_limit import limiter
from app.core.security import verify_password
from app.core.step_up import (
    STEP_UP_TTL_SECONDS,
    StepUpScope,
    available_methods,
    grant,
)
from app.core.webauthn import (
    WebAuthnVerificationError,
    authentication_options,
    sign_count_is_acceptable,
    verify_authentication,
)
from app.models.user import User
from app.models.webauthn import WebAuthnCredential

logger = logging.getLogger(__name__)

router = APIRouter()

_SCOPE = "step-up"


class OptionsIn(BaseModel):
    scope: StepUpScope


class OptionsOut(BaseModel):
    methods: list[str]
    scope: StepUpScope
    purpose: str
    """For the Nostr proof — the exact string that must sit inside the signed
    event, so a signature cannot be carried to another operation."""
    challenge: str | None = None
    """Nonce for the Nostr proof. `None` when the account cannot sign."""
    webauthn: dict | None = None
    """WebAuthn assertion options, or `None` if no passkey is registered."""
    expires_in: int = CHALLENGE_TTL_SECONDS


class VerifyIn(BaseModel):
    scope: StepUpScope
    # Exactly one of the four.
    password: str | None = None
    nostr: dict | None = None
    webauthn: dict | None = None
    contact_code: str | None = None

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str | None) -> str | None:
        return v or None


class VerifyOut(BaseModel):
    step_up_token: str
    scope: StepUpScope
    expires_in: int = STEP_UP_TTL_SECONDS


async def _credential_count(db: AsyncSession, user_id) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user_id)
        )
    ) or 0


def _challenge_subject(user_id, scope: StepUpScope) -> str:
    return f"{scope.value}:{user_id}"


@router.post("/options", response_model=OptionsOut)
@limiter.limit("30/hour")
async def step_up_options(
    request: Request,
    body: OptionsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.contacts import login_contact

    count = await _credential_count(db, current_user.id)
    contact = await login_contact(db, current_user.id)
    methods = available_methods(
        current_user, count, has_login_contact=contact is not None
    )
    if not methods:
        # Every way in is gone — a retired identity with no password and no
        # device. Nothing to confirm with, and no point pretending otherwise.
        raise HTTPException(
            status_code=409,
            detail="This account has no way to confirm an action",
        )

    # A proof the account can give only if we actually send it something. The
    # code goes out here, when the options are asked for, because that is the
    # moment the person is looking at the dialog — issuing it lazily on the
    # first wrong guess would mean the first guess is always wrong.
    if "contact_code" in methods and contact is not None:
        from app.core.contact_verification import CooldownActive, issue
        from app.tasks.notifications import send_channel_code

        try:
            code = await issue(
                db,
                contact.channel,
                contact.value,
                purpose="stepup",
                user_id=current_user.id,
            )
            await db.commit()
            send_channel_code.delay(contact.channel, contact.value, code, current_user.locale)
        except CooldownActive:
            # A code from moments ago is still live and still valid. Sending a
            # second would invalidate the one already in their hand.
            pass
        except Exception:
            logger.exception("could not send step-up code to %s", contact.value)

    subject = _challenge_subject(current_user.id, body.scope)
    challenge = None
    webauthn = None
    try:
        if "nostr" in methods:
            challenge = secrets.token_hex(32)
            await store_challenge(_SCOPE, subject, challenge)
        if "passkey" in methods:
            options_json, raw = authentication_options()
            webauthn = json.loads(options_json)
            await store_challenge(
                f"{_SCOPE}:webauthn", subject, bytes_to_base64url(raw)
            )
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")

    return OptionsOut(
        methods=methods,
        scope=body.scope,
        purpose=step_up_purpose(body.scope.value),
        challenge=challenge,
        webauthn=webauthn,
    )


async def _verify_contact_code(db, user, code: str) -> None:
    """T3.28 pt.3 — the proof an account created by a code can actually give.

    Deliberately its own `purpose`. A code that signs somebody in must not also
    authorise deleting their key, and a code issued to confirm a second address
    must not authorise anything at all — the three exist for different
    questions and `contact_verification` scopes every lookup by purpose.

    The attempt counter is committed before the refusal is raised. Letting the
    exception escape uncommitted would discard the increment and the limit
    would stop limiting.
    """
    from app.core.contact_verification import (
        CodeExpired,
        CodeInvalid,
        NoCodeIssued,
        TooManyAttempts,
        verify,
    )
    from app.core.contacts import login_contact

    contact = await login_contact(db, user.id)
    if contact is None:
        raise HTTPException(status_code=401, detail="Confirmation failed")
    try:
        await verify(db, contact.channel, contact.value, code, purpose="stepup")
    except (NoCodeIssued, CodeExpired, CodeInvalid):
        await db.commit()
        raise HTTPException(status_code=401, detail="Confirmation failed")
    except TooManyAttempts:
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many attempts")
    await db.commit()


@router.post("/verify", response_model=VerifyOut)
@limiter.limit("30/hour")
async def step_up_verify(
    request: Request,
    body: VerifyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    supplied = [
        p for p in (body.password, body.nostr, body.webauthn, body.contact_code) if p
    ]
    if len(supplied) != 1:
        raise HTTPException(
            status_code=422, detail="Provide exactly one proof"
        )

    if body.password is not None:
        if not current_user.password_hash or not verify_password(
            body.password, current_user.password_hash
        ):
            raise HTTPException(status_code=401, detail="Confirmation failed")

    elif body.nostr is not None:
        await _verify_nostr(current_user, body)

    elif body.contact_code is not None:
        await _verify_contact_code(db, current_user, body.contact_code)

    else:
        await _verify_webauthn(db, current_user, body)

    token = await grant(str(current_user.id), body.scope)
    return VerifyOut(step_up_token=token, scope=body.scope)


async def _verify_nostr(user: User, body: VerifyIn) -> None:
    if not user.key_self_custody or user.key_lost_at is not None:
        raise HTTPException(status_code=401, detail="Confirmation failed")
    try:
        stored = await take_challenge(
            _SCOPE, _challenge_subject(user.id, body.scope)
        )
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    if not stored:
        raise HTTPException(status_code=401, detail="Confirmation expired")

    proof = body.nostr or {}
    if proof.get("challenge") != stored:
        raise HTTPException(status_code=401, detail="Confirmation failed")
    # The signer must be *this* account: a valid signature by somebody else's
    # key proves nothing about who is at the keyboard here.
    if proof.get("npub_hex") != user.nostr_pubkey:
        raise HTTPException(status_code=401, detail="Confirmation failed")
    if not verify_proof(
        user.nostr_pubkey,
        step_up_purpose(body.scope.value),
        stored,
        int(proof.get("created_at") or 0),
        str(proof.get("sig") or ""),
        now=int(time.time()),
    ):
        raise HTTPException(status_code=401, detail="Confirmation failed")


async def _verify_webauthn(db: AsyncSession, user: User, body: VerifyIn) -> None:
    try:
        stored = await take_challenge(
            f"{_SCOPE}:webauthn", _challenge_subject(user.id, body.scope)
        )
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    if not stored:
        raise HTTPException(status_code=401, detail="Confirmation expired")

    credential = body.webauthn or {}
    raw_id = credential.get("rawId") or credential.get("id")
    if not raw_id:
        raise HTTPException(status_code=401, detail="Confirmation failed")
    try:
        credential_id = base64url_to_bytes(raw_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Confirmation failed")

    cred = (
        await db.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.credential_id == credential_id,
                # Scoped to this user: a passkey belonging to another account
                # must not confirm anything here, however valid its signature.
                WebAuthnCredential.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=401, detail="Confirmation failed")

    try:
        result = verify_authentication(
            credential=credential,
            expected_challenge=base64url_to_bytes(stored),
            public_key=bytes(cred.public_key),
            current_sign_count=cred.sign_count,
        )
    except WebAuthnVerificationError:
        raise HTTPException(status_code=401, detail="Confirmation failed")

    if not sign_count_is_acceptable(cred.sign_count, result.new_sign_count):
        raise HTTPException(
            status_code=401, detail="Authenticator counter regressed — possible clone"
        )
    cred.sign_count = result.new_sign_count
    await db.commit()
