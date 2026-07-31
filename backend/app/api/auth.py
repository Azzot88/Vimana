from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    target_email,
    verify_code,
)
from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.rate_limit import limiter
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.core.step_up import StepUpScope, consume as consume_step_up
from app.core.token_blacklist import blacklist_jti
from app.models.user import User
from app.schemas.user import (
    EmailChangeBody,
    EmailVerifyBody,
    MeOut,
    PasswordChangeBody,
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
    if not target_email(current_user):
        raise HTTPException(status_code=422, detail="Account has no email")
    # A change in flight always needs a code, even when the current address is
    # already verified — what is unproven is the pending one. Checking
    # `email_verified_at` alone would leave a started change with no way to
    # finish it.
    if current_user.pending_email is None and current_user.email_verified_at is not None:
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
    if current_user.pending_email is None and current_user.email_verified_at is not None:
        return {"status": "already_verified"}

    was_pending = current_user.pending_email

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

    try:
        await db.commit()
    except IntegrityError:
        # The pending address was claimed by someone else while this change was
        # in flight — a pending claim reserves nothing on purpose. The rollback
        # leaves the old address in place and still verified, so the account is
        # never left without a working one.
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="That address is now registered to another account"
        )

    if was_pending:
        return {"status": "changed", "email": current_user.email}
    return {"status": "verified"}


@router.post("/email/change", status_code=202)
@limiter.limit("5/hour")
async def change_email(
    request: Request,
    body: EmailChangeBody,
    step_up_token: str = Header(
        ..., alias="X-Step-Up-Token", description="From POST /api/auth/step-up/verify"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.15 — start a move to a new address. Nothing changes until it is proven.

    The account keeps its current address, verified and working, for the whole
    exchange. Two things follow from that. A typo costs a retry instead of the
    recovery channel — which matters because for many accounts email is the
    only way back in. And a stolen session cannot quietly redirect recovery
    mail: whoever holds it must also be able to read the new mailbox.
    """
    await consume_step_up(
        str(current_user.id), StepUpScope.CHANGE_EMAIL, step_up_token
    )

    if body.email == current_user.email:
        raise HTTPException(
            status_code=409, detail="That is already this account's address"
        )

    taken = await db.execute(select(User.id).where(User.email == body.email))
    if taken.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="email already registered")

    current_user.pending_email = body.email
    # A new address is a new code budget: the cooldown from an earlier request
    # must not block the first code of a change the user just confirmed.
    current_user.email_verification_sent_at = None
    try:
        _dispatch_code(current_user)
    except CooldownActive:  # pragma: no cover — cleared above, kept as a guard
        raise HTTPException(status_code=429, detail="Try again shortly")
    await db.commit()
    return {"status": "sent", "pending_email": body.email}


@router.delete("/email/pending", status_code=200)
async def cancel_email_change(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Abandon a pending change. No step-up: dropping a claim that was never
    proven only ever restores the state the account was already in."""
    if current_user.pending_email is None:
        return {"status": "nothing_pending"}

    current_user.pending_email = None
    # The outstanding code was minted for the address being abandoned. Leaving
    # it alive would let it later settle a claim about the current address.
    current_user.email_verification_code_hash = None
    current_user.email_verification_expires_at = None
    current_user.email_verification_attempts = 0
    await db.commit()
    return {"status": "cancelled"}


@router.put("/me/password", status_code=200)
@limiter.limit("10/hour")
async def change_password(
    request: Request,
    body: PasswordChangeBody,
    step_up_token: str = Header(
        ..., alias="X-Step-Up-Token", description="From POST /api/auth/step-up/verify"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.15 — set or replace the password.

    One endpoint for both because it is one operation to the user, and because
    an account with no password is not a lesser account: setting a first one is
    how a Nostr- or passkey-created account gains an email login.

    **Other sessions end here.** A password is usually changed because someone
    else may be holding a session, and those tokens cannot be revoked by `jti`
    — we never saw them. Setting `sessions_valid_from` retires every token
    issued before this moment instead.

    The caller gets a replacement token in the same response, so the device
    doing the change stays signed in. Without it the user would be thrown out
    by their own security action, which reads as a failure and invites a retry.
    """
    await consume_step_up(
        str(current_user.id), StepUpScope.CHANGE_PASSWORD, step_up_token
    )

    current_user.password_hash = hash_password(body.new_password)
    current_user.sessions_valid_from = datetime.now(timezone.utc)
    await db.commit()

    # Minted *after* the cutoff is stored, so its `iat` is strictly later and it
    # survives the retirement it is part of. Reordering these two lines would
    # log the user out of the device that just secured the account.
    replacement = create_access_token(str(current_user.id))
    return {
        "status": "changed",
        "access_token": replacement,
        "token_type": "bearer",
    }


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
