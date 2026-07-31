import uuid
from datetime import timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.token_blacklist import is_blacklisted
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token revoked")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not _issued_after_cutoff(user, payload.get("iat")):
        raise HTTPException(status_code=401, detail="Session ended")
    return user


def _issued_after_cutoff(user: User, iat) -> bool:
    """T3.15 — was this token minted after the account's sessions were retired?

    Unlike the `jti` blacklist this is **fail-closed by construction**: the
    cutoff lives in Postgres, which the request already touched to load the
    user, so there is no second store to be unavailable. A token that predates
    the cutoff — or carries no issue time at all, which is every token minted
    before this existed — is refused.

    Compared at sub-second precision, which is why `iat` is minted as a float
    (`core.security`). Whole seconds would leave every token issued in the same
    second as the retirement alive, and the replacement token is minted
    milliseconds after the cutoff — under second granularity the two would be
    indistinguishable.
    """
    cutoff = user.sessions_valid_from
    if cutoff is None:
        return True
    if iat is None:
        return False
    if cutoff.tzinfo is None:  # naive column read — same convention as elsewhere
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return float(iat) >= cutoff.timestamp()


def is_superuser(user: User) -> bool:
    """Convenience helper — superuser bypasses most role-scoped checks."""
    return user.role == "superuser"
