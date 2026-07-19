from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.keypair import encrypt_nsec, generate_keypair
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import MeOut, Token, UserCreate, UserLogin, UserOut, UserUpdate

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("60/minute")
async def register(request: Request, body: UserCreate, db: AsyncSession = Depends(get_db)):
    if not body.email and not body.phone:
        raise HTTPException(status_code=422, detail="email or phone is required")

    email = body.email.strip().lower() if body.email else None
    phone = body.phone.strip() if body.phone else None

    if email:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="email already registered")

    if phone:
        existing = await db.execute(select(User).where(User.phone == phone))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="phone already registered")

    # T2.2 — custodial Nostr keypair generated at registration.
    # `nsec_encrypted` is DELETE-ed later when user claims self-custody.
    nsec_hex, npub_hex = generate_keypair()
    nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)

    user = User(
        email=email,
        phone=phone,
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
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("60/minute")
async def login(request: Request, body: UserLogin, db: AsyncSession = Depends(get_db)):
    user: User | None = None
    login_val = body.login.strip()

    if "@" in login_val:
        email_lc = login_val.lower()
        result = await db.execute(select(User).where(User.email == email_lc))
        user = result.scalar_one_or_none()
    else:
        result = await db.execute(select(User).where(User.phone == login_val))
        user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=MeOut)
async def me(current_user: User = Depends(get_current_user)):
    """Owner view — includes private `receiving_*` fields."""
    return current_user


@router.patch("/me", response_model=MeOut)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user
