from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserOut, UserUpdate

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    if not body.email and not body.phone:
        raise HTTPException(status_code=422, detail="email or phone is required")

    if body.email:
        existing = await db.execute(select(User).where(User.email == body.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="email already registered")

    if body.phone:
        existing = await db.execute(select(User).where(User.phone == body.phone))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="phone already registered")

    user = User(
        email=body.email,
        phone=body.phone,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        is_carrier=body.is_carrier,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    user: User | None = None

    if "@" in body.login:
        result = await db.execute(select(User).where(User.email == body.login))
        user = result.scalar_one_or_none()
    else:
        result = await db.execute(select(User).where(User.phone == body.login))
        user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user
