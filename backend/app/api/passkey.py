"""T3.14 — passkey ceremonies: register, sign in, sign up, unlink.

A passkey authenticates a *device*; `users.nostr_pubkey` is the identity. Two
phones on one account are two rows here and one npub — which is the whole point
of the split.

**Ceremony state is keyed by a one-shot `ceremony_id`, not by user.** Login is
usernameless, so at options-time there is no user to key on; and even for
register, a user with two tabs open would otherwise have the second ceremony
overwrite the first. The id is meaningless on its own — the scope in the Redis
key stops a login challenge being spent on a registration.

No `from __future__ import annotations` in this module: combined with slowapi's
`@limiter.limit` it leaves annotations as strings, FastAPI stops recognising
Pydantic bodies and every request answers `422 {"loc": ["query", "body"]}`
(T3.13 lost an hour to exactly this).
"""

import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)

from app.api.deps import get_current_user
from app.core.challenge import (
    CHALLENGE_TTL_SECONDS,
    ChallengeUnavailable,
    store_challenge,
    take_challenge,
)
from app.core.database import get_db
from app.core.email_verification import (
    is_auto_verify_domain,
    is_valid_email,
    normalize_email,
)
from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.core.webauthn import (
    SCOPE_LOGIN,
    SCOPE_REGISTER,
    SCOPE_SIGNUP,
    authentication_options,
    describe_device,
    registration_options,
    sign_count_is_acceptable,
    verify_authentication,
    verify_registration,
    would_lock_the_user_out,
)
from app.models.user import User
from app.models.webauthn import WebAuthnCredential
from app.schemas.user import Token, UserOut

router = APIRouter()


class OptionsOut(BaseModel):
    """`options` is the raw JSON from py_webauthn — passed to the browser
    untouched, because the shape is the spec's, not ours."""

    ceremony_id: str
    options: dict
    expires_in: int


class SignupOptionsIn(BaseModel):
    display_name: str
    email: str | None = None

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


class VerifyIn(BaseModel):
    ceremony_id: str
    credential: dict
    device_name: str | None = None

    @field_validator("device_name")
    @classmethod
    def _device(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v[:100] or None


class CredentialOut(BaseModel):
    id: uuid.UUID
    device_name: str | None
    device_kind: str
    created_at: datetime
    last_used_at: datetime | None


class SignupOut(BaseModel):
    user: UserOut
    token: Token


def _new_ceremony_id() -> str:
    return secrets.token_hex(16)


async def _put(scope: str, payload: str) -> str:
    ceremony_id = _new_ceremony_id()
    try:
        await store_challenge(scope, ceremony_id, payload)
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    return ceremony_id


async def _take(scope: str, ceremony_id: str) -> str:
    try:
        stored = await take_challenge(scope, ceremony_id)
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    if not stored:
        raise HTTPException(status_code=401, detail="Ceremony is unknown or expired")
    return stored


# ── register a device on an existing account ─────────────────────────────────


@router.post("/register/options", response_model=OptionsOut)
@limiter.limit("20/hour")
async def register_options(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(
            select(WebAuthnCredential.credential_id).where(
                WebAuthnCredential.user_id == current_user.id
            )
        )
    ).scalars().all()

    options_json, challenge = registration_options(
        user_id_bytes=current_user.id.bytes,
        # Shown by the authenticator when picking an account. Falls back to the
        # npub for accounts with no email — a passkey account may have none.
        user_name=current_user.email or (current_user.nostr_pubkey or "")[:16],
        display_name=current_user.display_name,
        exclude_credential_ids=[bytes(c) for c in existing],
    )
    ceremony_id = await _put(SCOPE_REGISTER, bytes_to_base64url(challenge))
    return OptionsOut(
        ceremony_id=ceremony_id,
        options=json.loads(options_json),
        expires_in=CHALLENGE_TTL_SECONDS,
    )


@router.post("/register/verify", response_model=CredentialOut, status_code=201)
@limiter.limit("20/hour")
async def register_verify(
    request: Request,
    body: VerifyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stored = await _take(SCOPE_REGISTER, body.ceremony_id)
    try:
        result = verify_registration(
            credential=body.credential,
            expected_challenge=base64url_to_bytes(stored),
        )
    except (InvalidRegistrationResponse, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail=f"Registration failed: {exc}")

    taken = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == result.credential_id
        )
    )
    if taken.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This device is already registered")

    cred = _persist(db, current_user.id, result, body)
    await db.commit()
    await db.refresh(cred)
    return _to_out(cred)


def _persist(db, user_id, result, body: VerifyIn) -> WebAuthnCredential:
    transports = [t.value if hasattr(t, "value") else str(t) for t in (
        getattr(result, "credential_transports", None) or []
    )]
    cred = WebAuthnCredential(
        user_id=user_id,
        credential_id=result.credential_id,
        public_key=result.credential_public_key,
        sign_count=result.sign_count,
        transports=transports or None,
        aaguid=str(getattr(result, "aaguid", "") or "")[:36] or None,
        device_name=body.device_name,
        backed_up=bool(getattr(result, "credential_backed_up", False)),
        uv_capable=bool(getattr(result, "user_verified", False)),
    )
    db.add(cred)
    return cred


def _to_out(cred: WebAuthnCredential) -> CredentialOut:
    return CredentialOut(
        id=cred.id,
        device_name=cred.device_name,
        device_kind=describe_device(
            transports=cred.transports, backed_up=cred.backed_up
        ),
        created_at=cred.created_at,
        last_used_at=cred.last_used_at,
    )


# ── sign in ──────────────────────────────────────────────────────────────────


@router.post("/login/options", response_model=OptionsOut)
@limiter.limit("20/minute")
async def login_options(request: Request):
    """No auth and no user hint — `allowCredentials` is empty on purpose, so
    the endpoint cannot be used to ask "does this account exist"."""
    options_json, challenge = authentication_options()
    ceremony_id = await _put(SCOPE_LOGIN, bytes_to_base64url(challenge))
    return OptionsOut(
        ceremony_id=ceremony_id,
        options=json.loads(options_json),
        expires_in=CHALLENGE_TTL_SECONDS,
    )


@router.post("/login/verify", response_model=Token)
@limiter.limit("20/minute")
async def login_verify(
    request: Request, body: VerifyIn, db: AsyncSession = Depends(get_db)
):
    stored = await _take(SCOPE_LOGIN, body.ceremony_id)

    raw_id = body.credential.get("rawId") or body.credential.get("id")
    if not raw_id:
        raise HTTPException(status_code=422, detail="Credential has no id")
    try:
        credential_id = base64url_to_bytes(raw_id)
    except Exception:
        raise HTTPException(status_code=422, detail="Malformed credential id")

    cred = (
        await db.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.credential_id == credential_id
            )
        )
    ).scalar_one_or_none()
    # Same 401 as a bad signature: telling an unknown credential apart from an
    # invalid one would answer "is this device registered here" for free.
    if cred is None:
        raise HTTPException(status_code=401, detail="Authentication failed")

    try:
        result = verify_authentication(
            credential=body.credential,
            expected_challenge=base64url_to_bytes(stored),
            public_key=bytes(cred.public_key),
            current_sign_count=cred.sign_count,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Authentication failed")

    if not sign_count_is_acceptable(cred.sign_count, result.new_sign_count):
        # Counter went backwards on an authenticator that keeps one — two
        # devices are presenting the same credential.
        raise HTTPException(
            status_code=401, detail="Authenticator counter regressed — possible clone"
        )

    user = await db.get(User, cred.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication failed")
    if user.key_lost_at is not None:
        raise HTTPException(
            status_code=403,
            detail="Identity key was declared lost — this account is retired",
        )

    cred.sign_count = result.new_sign_count
    cred.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return Token(access_token=create_access_token(str(user.id)))


# ── sign up ──────────────────────────────────────────────────────────────────


@router.post("/signup/options", response_model=OptionsOut)
@limiter.limit("10/hour")
async def signup_options(request: Request, body: SignupOptionsIn):
    """The account does not exist yet, so its id is minted here and carried
    through the ceremony — the authenticator stores it as the user handle, and
    it has to be the id the row ends up with."""
    pending_id = uuid.uuid4()
    options_json, challenge = registration_options(
        user_id_bytes=pending_id.bytes,
        user_name=body.email or body.display_name,
        display_name=body.display_name,
        exclude_credential_ids=[],
    )
    payload = json.dumps(
        {
            "challenge": bytes_to_base64url(challenge),
            "user_id": str(pending_id),
            "display_name": body.display_name,
            "email": body.email,
        }
    )
    ceremony_id = await _put(SCOPE_SIGNUP, payload)
    return OptionsOut(
        ceremony_id=ceremony_id,
        options=json.loads(options_json),
        expires_in=CHALLENGE_TTL_SECONDS,
    )


@router.post("/signup/verify", response_model=SignupOut, status_code=201)
@limiter.limit("10/hour")
async def signup_verify(
    request: Request, body: VerifyIn, db: AsyncSession = Depends(get_db)
):
    pending = json.loads(await _take(SCOPE_SIGNUP, body.ceremony_id))

    try:
        result = verify_registration(
            credential=body.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
        )
    except (InvalidRegistrationResponse, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail=f"Registration failed: {exc}")

    taken = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == result.credential_id
        )
    )
    if taken.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This device already has an account")

    email = pending.get("email")
    if email:
        clash = await db.execute(select(User).where(User.email == email))
        if clash.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="email already registered")

    # Service keypair, exactly as `register` does. Not an identity: the user
    # gets their own later through `POST /me/identity/establish`, and that is
    # always a *new* key — `claim` was removed in T3.12 precisely because a key
    # the platform once held cannot be called sovereign.
    nsec_hex, npub_hex = generate_keypair()
    nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)

    user = User(
        id=uuid.UUID(pending["user_id"]),
        email=email,
        password_hash=None,
        display_name=pending["display_name"],
        nostr_pubkey=npub_hex,
        nsec_encrypted=nsec_ct,
        nsec_nonce=nsec_nonce,
        key_self_custody=False,
    )
    if email and is_auto_verify_domain(email):
        user.email_verified_at = datetime.now(timezone.utc)
    db.add(user)
    await db.flush()

    _persist(db, user.id, result, body)
    await db.commit()
    await db.refresh(user)

    if user.email and user.email_verified_at is None:
        from app.api.auth import _dispatch_code

        _dispatch_code(user)
        await db.commit()

    # A token, not just the row: there is no password to sign in with after.
    return SignupOut(
        user=UserOut.model_validate(user, from_attributes=True),
        token=Token(access_token=create_access_token(str(user.id))),
    )


# ── manage devices ───────────────────────────────────────────────────────────


@router.get("", response_model=list[CredentialOut])
async def list_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == current_user.id)
            .order_by(WebAuthnCredential.created_at)
        )
    ).scalars().all()
    return [_to_out(c) for c in rows]


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cred = await db.get(WebAuthnCredential, credential_id)
    if cred is None or cred.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Credential not found")

    total = (
        await db.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.user_id == current_user.id
            )
        )
    ).scalars().all()

    if would_lock_the_user_out(current_user, credential_count=len(total)):
        # Not a logout — the account would become unreachable, and with email
        # optional there may be no way back at all.
        raise HTTPException(
            status_code=409,
            detail="This is your last way to sign in — add another before removing it",
        )

    await db.delete(cred)
    await db.commit()
