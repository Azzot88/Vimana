from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.avatar_url import me_out_with_avatar
from app.core.database import get_db
from app.core.email_verification import (
    RESEND_COOLDOWN,
    CodeExpired,
    CodeInvalid,
    CooldownActive,
    NoCodeIssued,
    TooManyAttempts,
    is_auto_verify_domain,
    issue_code,
    normalize_email,
    verify_code,
)
from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.rate_limit import limiter
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.core.token_blacklist import blacklist_jti
from app.models.user import User
from app.schemas.user import (
    EmailVerifyBody,
    MeOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("60/minute")
async def register(request: Request, body: UserCreate, db: AsyncSession = Depends(get_db)):
    email = body.email  # normalized + shape-checked by the schema validator

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="email already registered")

    # T2.2 — custodial Nostr keypair generated at registration.
    # `nsec_encrypted` is DELETE-ed later when user claims self-custody.
    nsec_hex, npub_hex = generate_keypair()
    nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        can_carry=body.can_carry,
        can_send=body.can_send,
        active_mode=body.active_mode,
        nostr_pubkey=npub_hex,
        nsec_encrypted=nsec_ct,
        nsec_nonce=nsec_nonce,
        key_self_custody=False,
    )
    # T3.11 — E2E domain bypasses the mailbox entirely (empty setting in prod).
    if is_auto_verify_domain(email):
        user.email_verified_at = datetime.now(timezone.utc)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    if user.email_verified_at is None:
        _dispatch_code(user)
        await db.commit()

    return user


def _dispatch_code(user: User) -> None:
    """Mint a code and hand it to Celery. Caller commits.

    The plaintext travels through the broker because it exists nowhere else —
    the column holds only a bcrypt hash. It is single-use and expires in
    `CODE_TTL`.
    """
    code = issue_code(user)
    from app.tasks.notifications import send_verification_code

    try:
        send_verification_code.delay(str(user.id), code)
    except Exception:
        # Broker unreachable in dev — the code is still stamped on the user and
        # can be re-requested once the cooldown passes.
        pass


@router.post("/email/request-code", status_code=202)
@limiter.limit("5/hour")
async def request_email_code(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent-ish: already-verified is a 200-shaped no-op, not an error."""
    if not current_user.email:
        raise HTTPException(status_code=422, detail="Account has no email")
    if current_user.email_verified_at is not None:
        return {"status": "already_verified"}

    try:
        _dispatch_code(current_user)
    except CooldownActive:
        raise HTTPException(
            status_code=429,
            detail=f"Wait {int(RESEND_COOLDOWN.total_seconds())}s before requesting a new code",
        )
    await db.commit()
    return {"status": "sent"}


@router.post("/email/verify")
@limiter.limit("20/hour")
async def verify_email(
    request: Request,
    body: EmailVerifyBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.email_verified_at is not None:
        return {"status": "already_verified"}

    try:
        verify_code(current_user, body.code)
    except (NoCodeIssued, CodeExpired) as exc:
        await db.commit()  # persist the cleared code state
        detail = "No code issued" if isinstance(exc, NoCodeIssued) else "Code expired"
        raise HTTPException(status_code=400, detail=detail)
    except TooManyAttempts:
        await db.commit()
        raise HTTPException(
            status_code=429, detail="Too many attempts — request a new code"
        )
    except CodeInvalid:
        await db.commit()  # persist the incremented attempt counter
        raise HTTPException(status_code=400, detail="Invalid code")

    await db.commit()
    return {"status": "verified"}


@router.post("/login", response_model=Token)
@limiter.limit("60/minute")
async def login(request: Request, body: UserLogin, db: AsyncSession = Depends(get_db)):
    # T3.11 — email only. The phone branch is gone; a phone-shaped login simply
    # matches nothing and falls through to the same 401 as a wrong password.
    result = await db.execute(
        select(User).where(User.email == normalize_email(body.login))
    )
    user = result.scalar_one_or_none()

    # `password_hash` is nullable since T3.11 — a Nostr/Passkey account has no
    # password and must not be loggable through this route at all.
    if not user or not user.password_hash or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.post("/logout", status_code=204)
async def logout(token: str = Depends(_oauth2_scheme)):
    """T_UX.3 pt.4a — revoke the presenting JWT via Redis blacklist.

    Idempotent by nature: an already-invalid or already-blacklisted token
    resolves to a no-op 204. We decode with jwt directly (not
    `get_current_user`) so an expired token still gets a clean 204 response
    — no point in erroring out on logout of a dead token.
    """
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return  # invalid/expired — nothing to revoke, client can drop token
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    ttl = int(exp - datetime.now(timezone.utc).timestamp())
    await blacklist_jti(jti, ttl)


@router.get("/me", response_model=MeOut)
async def me(current_user: User = Depends(get_current_user)):
    """Owner view — includes private `receiving_*` fields + presigned avatar URL."""
    return me_out_with_avatar(current_user)


_NOT_NULL_UPDATE_FIELDS = {
    "display_name",
    "notify_email",
    "notify_telegram",
    "notify_whatsapp",
    "active_mode",
    "can_carry",
    "can_send",
}


@router.patch("/me", response_model=MeOut)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field in _NOT_NULL_UPDATE_FIELDS:
            raise HTTPException(
                status_code=422, detail=f"'{field}' cannot be null"
            )
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return me_out_with_avatar(current_user)
