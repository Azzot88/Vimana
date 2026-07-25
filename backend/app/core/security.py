import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException

from app.core.config import settings

_ALGORITHM = "HS256"
_DEFAULT_EXPIRE_DAYS = 30

# Work factor for password hashing. 12 (bcrypt default) in production — the
# cost is the only thing standing between a leaked DB dump and a brute force.
# The test process sets BCRYPT_ROUNDS=4 (~1 ms) via conftest env: same
# algorithm, same verify path, just without the deliberate slowness — hundreds
# of register/login calls per suite made 12 rounds the dominant test cost.
_BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """Signs a JWT with a random `jti` so it can be individually revoked
    (T_UX.3 pt.4a — Redis blacklist)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(days=_DEFAULT_EXPIRE_DAYS)
    )
    payload = {"sub": subject, "exp": expire, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decodes and validates a JWT. Returns the payload dict on success,
    raises 401 on invalid/expired signature or missing `sub`."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
        if payload.get("sub") is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
