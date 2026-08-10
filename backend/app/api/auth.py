import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    RECOVERY_SCOPE,
    get_current_user,
    get_recovery_or_current_user,
)
from app.core.avatar_url import me_out_with_avatar
from app.core.database import get_db
from app.core.contacts import upsert_contact
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
from app.core.security import (
    RECOVERY_CODE_COUNT,
    create_access_token,
    decode_access_token,
    generate_recovery_code,
    hash_password,
    hash_recovery_code,
    verify_password,
)
from app.core.step_up import StepUpScope, consume as consume_step_up, grant as grant_step_up
from app.core.token_blacklist import blacklist_jti
from app.models.user import RecoveryCode, User
from app.schemas.user import (
    EmailChangeBody,
    EmailVerifyBody,
    MeOut,
    PasswordChangeBody,
    RecoveryCodesOut,
    RecoveryConsumeBody,
    RecoverySessionOut,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

logger = logging.getLogger(__name__)

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
        locale=body.locale,
        nostr_pubkey=npub_hex,
        nsec_encrypted=nsec_ct,
        nsec_nonce=nsec_nonce,
        key_self_custody=False,
    )
    # T3.11 — E2E domain bypasses the mailbox entirely (empty setting in prod).
    if is_auto_verify_domain(email):
        user.email_verified_at = datetime.now(timezone.utc)

    db.add(user)
    # Flushed before the contact row: `user.id` is assigned at flush, and
    # `upsert_contact` writes a foreign key to it.
    await db.flush()
    # T3.25 — the same fact in the table that will own it. Verified only if the
    # address really is: at ordinary registration nobody has proved anything
    # yet, and writing `verified` here would put the first lie into the column
    # the whole table exists to make trustworthy.
    registered_contact = await upsert_contact(
        db, user, "email", user.email, verified=user.email_verified_at is not None
    )
    # T3.28 — this address is how the account signs in. The 0045 backfill set
    # the flag for every account that predates contacts; without setting it
    # here, accounts created after the migration would be the only ones unable
    # to use a code to get in.
    if registered_contact is not None:
        registered_contact.is_login = True
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
        # T3.25 — a confirmation is exactly the event `user_contacts` records.
        # Inside the `try`, not before it: this SELECT autoflushes the pending
        # address change, so when the address was claimed by someone else mid
        # flight the IntegrityError now surfaces here rather than at the commit
        # below — and it must be caught by the same handler either way.
        await upsert_contact(
            db, current_user, "email", current_user.email, verified=True
        )
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
    # T3.16 — also reachable with a recovery-scoped token: setting a password is
    # one of the two doors a locked-out account has left, and the step-up grant
    # that comes with a consumed code is what authorises it.
    current_user: User = Depends(get_recovery_or_current_user),
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

    _announce_password_change(current_user.id)

    # Minted *after* the cutoff is stored, so its `iat` is strictly later and it
    # survives the retirement it is part of. Reordering these two lines would
    # log the user out of the device that just secured the account.
    replacement = create_access_token(str(current_user.id))
    return {
        "status": "changed",
        "access_token": replacement,
        "token_type": "bearer",
    }


def _announce_password_change(user_id) -> None:
    """T_SEC.5 pt.2 — one announcement, both doors.

    The profile and the reset link are one event to the mailbox: the account
    now opens with something else. Dispatched from a helper rather than copied
    into both handlers so a third door cannot be added silently.

    Called by: `change_password`, `reset_password`.
    """
    from app.tasks.notifications import send_password_changed

    try:
        send_password_changed.delay(str(user_id))
    except Exception:
        logger.exception("could not queue password-changed notice for %s", user_id)


class OtpRequestBody(BaseModel):
    identifier: str
    channel: str
    locale: str = "en"


class OtpVerifyBody(BaseModel):
    identifier: str
    code: str
    # T3.28 pt.4 — a password typed on the sign-in screen, carried by the
    # browser until the code proves the address. Applied **only** when the code
    # creates the account; see `otp_verify`.
    password: str | None = None


@router.post("/otp/request", status_code=202)
@limiter.limit("10/hour")
async def otp_request(
    request: Request, body: OtpRequestBody, db: AsyncSession = Depends(get_db)
):
    """T3.28 — one door for signing in and signing up. Answers 202 always.

    The same answer whether the identifier belongs to an account, belongs to
    nobody, is unusable, or names a channel we do not run. Anything else makes
    a public form into an oracle: type an address, read the status, learn
    whether that person banks here. That is the single most valuable thing an
    attacker can get from a login screen and it costs them nothing.

    Deliberately separate from `/contact/request-code`: same machinery, but the
    purposes must not be interchangeable. A code minted to add a second address
    to an existing account must never be spendable to *become* that account —
    so `purpose` differs, and `contact_verification` scopes every lookup by it.
    """
    from app.core.channels import available_for
    from app.core.contact_verification import CooldownActive, issue
    from app.core.contacts import normalize

    if body.channel not in available_for(body.identifier):
        return {"status": "accepted"}

    value = normalize("email" if body.channel == "email" else "sms", body.identifier)
    if value is None:
        return {"status": "accepted"}

    try:
        code = await issue(db, body.channel, value, purpose="login")
    except CooldownActive:
        raise HTTPException(status_code=429, detail="A code was sent moments ago")
    await db.commit()

    from app.tasks.notifications import send_channel_code

    try:
        send_channel_code.delay(body.channel, value, code, body.locale)
    except Exception:
        logger.exception("could not queue login code for %s", value)

    return {"status": "accepted"}


@router.post("/otp/verify", response_model=Token)
@limiter.limit("20/hour")
async def otp_verify(
    request: Request, body: OtpVerifyBody, db: AsyncSession = Depends(get_db)
):
    """T3.28 — spend the code: sign in, or become an account.

    One endpoint for both because to the person it is one act — they proved
    they can read this address, and what happens next is our bookkeeping, not
    their decision. Splitting it would also mean a screen that has to know, and
    therefore say, whether the address is already registered.

    **A provisional display name is written, not asked for here.** Refusing to
    finish without one would burn the code the visitor just spent, and a code
    consumed for nothing is the worst possible answer to a correct one. The
    onboarding screen renames the account immediately afterwards.

    The account is created exactly as `register` creates one — service keypair
    included (T3.12) — because an account that arrived through a different door
    must not be a different kind of account.
    """
    from app.core.channels import proves
    from app.core.contact_verification import (
        CodeExpired,
        CodeInvalid,
        NoCodeIssued,
        TooManyAttempts,
        verify,
    )
    from app.core.contacts import normalize, upsert_contact
    from app.models.contact import UserContact

    for channel in ("email", "sms", "whatsapp", "telegram_gateway"):
        value = normalize("email" if channel == "email" else "sms", body.identifier)
        if value is None:
            continue
        try:
            await verify(db, channel, value, body.code, purpose="login")
        except NoCodeIssued:
            continue
        except CodeExpired:
            await db.commit()
            raise HTTPException(status_code=400, detail="Code expired")
        except TooManyAttempts:
            await db.commit()
            raise HTTPException(
                status_code=429, detail="Too many attempts — request a new code"
            )
        except CodeInvalid:
            await db.commit()
            raise HTTPException(status_code=400, detail="Invalid code")

        contact_channel = proves(channel)
        owner_id = (
            await db.execute(
                select(UserContact.user_id).where(
                    UserContact.channel == contact_channel,
                    UserContact.value == value,
                    UserContact.verified_at.isnot(None),
                    UserContact.is_login.is_(True),
                )
            )
        ).scalar_one_or_none()

        if owner_id:
            user = await db.get(User, owner_id)
            # A password typed alongside the code is **ignored** for an account
            # that already exists. The code proves the address, and the address
            # is the recovery channel — so honouring it here would be a silent
            # password reset performed by whoever holds the mailbox, with no
            # screen saying so. Resetting a password has its own flow that says
            # what it is doing (`T_SEC.5`).
            pass
        else:
            nsec_hex, npub_hex = generate_keypair()
            nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)
            user = User(
                email=value if contact_channel == "email" else None,
                phone=value if contact_channel == "sms" else None,
                password_hash=None,
                # Provisional, and replaced on the next screen. The local part
                # of an address is a better first guess than "User" and a worse
                # one than what the person will type.
                display_name=value.split("@")[0][:100],
                nostr_pubkey=npub_hex,
                nsec_encrypted=nsec_ct,
                nsec_nonce=nsec_nonce,
                key_self_custody=False,
            )
            if contact_channel == "email":
                user.email_verified_at = datetime.now(timezone.utc)
            # The account is born with the password the visitor typed a moment
            # ago on the same screen, if they typed one. Nothing was stored
            # before this point: an account created on an unproven address is
            # how a stranger squats on somebody else's, and a typo would have
            # produced a second account instead of an error.
            if body.password:
                user.password_hash = hash_password(body.password)
            db.add(user)
            await db.flush()
            contact = await upsert_contact(
                db, user, contact_channel, value, verified=True
            )
            if contact is not None:
                contact.is_login = True

        await db.commit()
        return {"access_token": create_access_token(str(user.id)), "token_type": "bearer"}

    raise HTTPException(status_code=400, detail="Invalid or expired code")


class ChannelsBody(BaseModel):
    identifier: str


class ContactCodeBody(BaseModel):
    identifier: str
    channel: str


class ContactConfirmBody(BaseModel):
    identifier: str
    code: str


@router.post("/contact/channels", status_code=200)
@limiter.limit("30/hour")
async def contact_channels(request: Request, body: ChannelsBody):
    """T3.26 — which channels can confirm this identifier, right now.

    Answers about the *identifier*, not about any account: whether somebody
    already registered with it is none of this endpoint's business, and saying
    so would make a public form into a directory.

    An email address gets `email`; a phone gets the channels that reach the
    number itself. `telegram` is deliberately absent for a phone — pressing
    Start proves control of a Telegram account, never of the number typed a
    minute earlier (see `core/channels`).
    """
    from app.core.channels import available_for

    return {"channels": available_for(body.identifier)}


@router.post("/contact/request-code", status_code=202)
@limiter.limit("10/hour")
async def request_contact_code(
    request: Request, body: ContactCodeBody, db: AsyncSession = Depends(get_db)
):
    """T3.26/T3.27 — send a code to a contact. 202 whatever happens.

    The same answer for an unusable identifier, a channel that is switched off
    and a transport that failed. A caller cannot learn from this endpoint which
    numbers exist, which channels we pay for, or whether our SMS provider is
    down — and none of those are things a stranger should be able to enumerate.

    The cooldown is the one exception that answers differently (429), because
    it is about the caller's own last request and telling them to wait is the
    entire point of it.
    """
    from app.core.channels import available_for, deliver
    from app.core.contact_verification import CooldownActive, issue
    from app.core.contacts import normalize

    channel = body.channel
    if channel not in available_for(body.identifier):
        return {"status": "accepted"}

    value = normalize("email" if channel == "email" else "sms", body.identifier)
    if value is None:
        return {"status": "accepted"}

    try:
        code = await issue(db, channel, value)
    except CooldownActive:
        raise HTTPException(status_code=429, detail="A code was sent moments ago")
    await db.commit()

    from app.tasks.notifications import send_channel_code

    try:
        send_channel_code.delay(channel, value, code, None)
    except Exception:
        logger.exception("could not queue %s code for %s", channel, value)

    return {"status": "accepted"}


@router.post("/contact/confirm", status_code=200)
@limiter.limit("20/hour")
async def confirm_contact_code(
    request: Request,
    body: ContactConfirmBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.26 — a confirmed code turns the identifier into a confirmed contact.

    Requires a session for now. Signing *in* with a code is `T3.28`; this is
    the smaller half — an account proving it owns a second way to be reached —
    and shipping it first keeps the code machinery exercised by something real
    instead of by tests alone.

    The attempt counter is committed on a wrong code. `contact_verification`
    increments it on the session and raises; a handler that let the exception
    escape without committing would throw the increment away and the limit
    would stop limiting.
    """
    from app.core.channels import proves
    from app.core.contact_verification import (
        CodeExpired,
        CodeInvalid,
        NoCodeIssued,
        TooManyAttempts,
        verify,
    )
    from app.core.contacts import normalize, upsert_contact

    for channel in ("email", "sms", "whatsapp", "telegram_gateway"):
        value = normalize("email" if channel == "email" else "sms", body.identifier)
        if value is None:
            continue
        try:
            await verify(db, channel, value, body.code)
        except NoCodeIssued:
            continue
        except CodeExpired:
            await db.commit()
            raise HTTPException(status_code=400, detail="Code expired")
        except TooManyAttempts:
            await db.commit()
            raise HTTPException(
                status_code=429, detail="Too many attempts — request a new code"
            )
        except CodeInvalid:
            await db.commit()
            raise HTTPException(status_code=400, detail="Invalid code")

        contact_channel = proves(channel)
        await upsert_contact(db, current_user, contact_channel, value, verified=True)
        await db.commit()
        return {"status": "confirmed", "channel": contact_channel}

    raise HTTPException(status_code=400, detail="No code issued")


class ForgotBody(BaseModel):
    identifier: str


class ResetBody(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def long_enough(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class MethodsBody(BaseModel):
    identifier: str


@router.post("/password/forgot", status_code=202)
@limiter.limit("5/hour")
async def forgot_password(
    request: Request, body: ForgotBody, db: AsyncSession = Depends(get_db)
):
    """T_SEC.5 — start a password reset. Answers 202 no matter what.

    Identical answer for an unknown address, a known one, an account with no
    password and one whose address is unverified. The alternative turns a
    public form into a directory of who banks here — and the useful half of
    that leak is free for the attacker and costly for everyone else.

    That silence has a price worth naming: someone whose address is not
    verified gets no letter and no explanation. It is the right trade anyway —
    a reset link is the account, and sending it to an address nobody proved
    they read would let anyone who typed your address take the account.
    """
    from app.core.password_reset import issue_token, reset_target

    identifier = normalize_email(body.identifier)
    result = await db.execute(select(User).where(User.email == identifier))
    user = result.scalar_one_or_none()

    # No password to reset is not a reason to say anything different out loud;
    # it is a reason not to send a letter that would confuse a passkey user.
    if user and user.password_hash and reset_target(user):
        token = issue_token(user)
        await db.commit()
        from app.tasks.notifications import send_password_reset

        try:
            send_password_reset.delay(str(user.id), token)
        except Exception:
            logger.exception("could not queue password reset for %s", user.id)

    return {"status": "accepted"}


@router.post("/password/reset")
@limiter.limit("10/hour")
async def reset_password(
    request: Request, body: ResetBody, db: AsyncSession = Depends(get_db)
):
    """T_SEC.5 — finish the reset and hand back a session.

    Every other session ends here, exactly as in `change_password` and for a
    sharper reason: a reset is what someone does when they suspect the account
    is not only theirs.

    The caller is signed in immediately. Making them type the password they
    just chose, into the screen that just took it, is a step that protects
    nobody.
    """
    from app.core.password_reset import ResetError, consume_token

    # The token identifies nothing by itself — it is scoped to a user, so the
    # row is found by the hash comparison, not by the token. Candidates are the
    # accounts with a pending reset; there is never more than a handful.
    result = await db.execute(
        select(User).where(User.password_reset_hash.isnot(None))
    )
    for candidate in result.scalars().all():
        try:
            consume_token(candidate, body.token)
        except ResetError:
            continue

        candidate.password_hash = hash_password(body.new_password)
        candidate.sessions_valid_from = datetime.now(timezone.utc)
        await db.commit()

        _announce_password_change(candidate.id)
        return {
            "status": "reset",
            "access_token": create_access_token(str(candidate.id)),
            "token_type": "bearer",
        }

    raise HTTPException(status_code=400, detail="Invalid or expired reset link")


@router.post("/methods", status_code=200)
@limiter.limit("30/hour")
async def login_methods(
    request: Request, body: MethodsBody, db: AsyncSession = Depends(get_db)
):
    """T_SEC.5 — which ways in this identifier can actually use.

    The sign-in screen offered a recovery code to every account, including the
    overwhelming majority who never made one, and offered nothing else to an
    account that had only a password to forget. Behind the login, step-up has
    answered this question correctly since T3.15 (`core.step_up.available_methods`);
    this is the same question asked from outside.

    **An unknown identifier gets the most ordinary answer** — password plus
    reset — rather than an empty list. It still leaks something: offering a
    passkey admits one exists. That is unavoidable if the screen is to be
    usable at all, and it is bounded by the rate limit; answering "no such
    account" would be worse and answering nothing would put us back where we
    started.
    """
    from app.core.step_up import available_methods
    from app.models.webauthn import WebAuthnCredential

    identifier = normalize_email(body.identifier)
    result = await db.execute(select(User).where(User.email == identifier))
    user = result.scalar_one_or_none()

    if not user:
        return {"methods": ["password"], "can_reset": True}

    count = (
        await db.execute(
            select(func.count(WebAuthnCredential.id)).where(
                WebAuthnCredential.user_id == user.id
            )
        )
    ).scalar() or 0

    methods = available_methods(user, count)
    has_codes = (
        await db.execute(
            select(func.count(RecoveryCode.id)).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        )
    ).scalar() or 0
    if has_codes:
        methods.append("recovery_code")

    from app.core.password_reset import reset_target

    return {
        "methods": methods,
        "can_reset": bool(user.password_hash and reset_target(user)),
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
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner view — includes private `receiving_*` fields + presigned avatar URL."""
    out = me_out_with_avatar(current_user)
    # T3.16 — counted here rather than kept as a column: a denormalised counter
    # would be a second truth about the same rows, and the query is a COUNT over
    # at most ten indexed rows.
    out.recovery_codes_remaining = int(
        (
            await db.execute(
                select(func.count(RecoveryCode.id)).where(
                    RecoveryCode.user_id == current_user.id,
                    RecoveryCode.used_at.is_(None),
                )
            )
        ).scalar()
        or 0
    )
    return out


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
    fields = body.model_dump(exclude_unset=True)
    # T3.19 — a closed archive outranks the visibility setting, so accepting a
    # write to it here would leave a control that reports one thing while
    # `visible_to` does another. Refusing loudly is the only honest option: the
    # UI hides the setting, and anything reaching this line is not the UI.
    if "public_profile" in fields and current_user.archive_choice == "hide":
        raise HTTPException(
            status_code=409, detail="The archive is closed — that choice is final"
        )
    for field, value in fields.items():
        if value is None and field in _NOT_NULL_UPDATE_FIELDS:
            raise HTTPException(
                status_code=422, detail=f"'{field}' cannot be null"
            )
        setattr(current_user, field, value)

    # T3.25 — a phone edited in the profile becomes a contact row, unverified.
    # Nobody has confirmed it: there is no mechanism yet (that is `T3.26`), and
    # writing `verified` for a number the account merely typed would put the
    # first untrue value into the column the table exists to make trustworthy.
    if "phone" in fields and fields["phone"]:
        await upsert_contact(db, current_user, "sms", fields["phone"], verified=False)

    await db.commit()
    await db.refresh(current_user)
    return me_out_with_avatar(current_user)


# ─────────────────────────────────────────────────────────────
# T3.16 — recovery codes: a spare way in, never a spare identity
# ─────────────────────────────────────────────────────────────


@router.post("/recovery/codes", response_model=RecoveryCodesOut)
@limiter.limit("10/hour")
async def issue_recovery_codes(
    request: Request,
    step_up_token: str = Header(
        ..., alias="X-Step-Up-Token", description="From POST /api/auth/step-up/verify"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate ten codes, shown exactly once, replacing any previous set.

    One endpoint for the first set and every later one: to the user it is the
    same action, and a separate "regenerate" would only add a state to explain.
    Under step-up in both cases — codes minted from a stolen session would
    outlive the password change that was supposed to end it.
    """
    await consume_step_up(
        str(current_user.id), StepUpScope.ADD_AUTH_METHOD, step_up_token
    )

    # Previous codes die with the new set, in the same transaction: two live
    # sets would mean a code the user believes replaced still opens the door.
    await db.execute(
        RecoveryCode.__table__.delete().where(RecoveryCode.user_id == current_user.id)
    )

    plaintext = [generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code in plaintext:
        db.add(RecoveryCode(user_id=current_user.id, code_hash=hash_recovery_code(code)))
    await db.commit()

    # The only moment these strings exist outside the user's hands.
    return RecoveryCodesOut(codes=plaintext, generated_at=datetime.now(timezone.utc))


@router.post("/recovery/consume", response_model=RecoverySessionOut)
@limiter.limit("5/hour")
async def consume_recovery_code(
    request: Request,
    body: RecoveryConsumeBody,
    db: AsyncSession = Depends(get_db),
):
    """Spend one code; get back the ability to bind a new way in — nothing more.

    The token returned here carries a scope, and `get_current_user` refuses
    scoped tokens outright: it opens exactly the two doors a locked-out person
    needs (set a password, register a passkey) and no others. A stolen code
    therefore does not become a full session.

    It also hands out step-up grants, because consuming a one-time code the user
    wrote down *is* the proof step-up asks for — and the accounts most likely to
    need this have no other proof left to give.

    Every failure answers the same 401. Distinguishing "no such account" from
    "wrong code" would turn this into a lookup service for which identifiers
    exist.
    """
    invalid = HTTPException(status_code=401, detail="Invalid identifier or code")

    identifier = (body.identifier or "").strip()
    if not identifier:
        raise invalid
    lookup = normalize_email(identifier) if "@" in identifier else identifier.lower()
    column = User.email if "@" in identifier else User.nostr_pubkey
    user = (
        await db.execute(select(User).where(column == lookup))
    ).scalars().first()
    if user is None:
        raise invalid

    digest = hash_recovery_code(body.code)
    row = (
        await db.execute(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == digest,
                RecoveryCode.used_at.is_(None),
            )
        )
    ).scalars().first()
    if row is None:
        raise invalid

    row.used_at = datetime.now(timezone.utc)
    # Flushed explicitly rather than leaning on autoflush: the count below must
    # already exclude the code being spent, and "it works because of a session
    # default" is the kind of thing that changes under you.
    await db.flush()
    remaining = (
        await db.execute(
            select(func.count(RecoveryCode.id)).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.used_at.is_(None),
            )
        )
    ).scalar() or 0
    await db.commit()

    # The owner hears about it even if it was not them — especially if it was
    # not them. Fire-and-forget: a broker hiccup must not fail a recovery.
    if user.email:
        from app.tasks.notifications import send_recovery_code_used

        try:
            send_recovery_code_used.delay(str(user.id), int(remaining))
        except Exception:
            pass

    token = create_access_token(
        str(user.id), expires_delta=timedelta(minutes=15), scope=RECOVERY_SCOPE
    )
    step_up_tokens = {
        StepUpScope.CHANGE_PASSWORD.value: await grant_step_up(
            str(user.id), StepUpScope.CHANGE_PASSWORD
        ),
        StepUpScope.ADD_AUTH_METHOD.value: await grant_step_up(
            str(user.id), StepUpScope.ADD_AUTH_METHOD
        ),
    }
    return RecoverySessionOut(
        access_token=token,
        scope=RECOVERY_SCOPE,
        codes_remaining=int(remaining),
        step_up_tokens=step_up_tokens,
    )
