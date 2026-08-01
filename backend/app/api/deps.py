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


RECOVERY_SCOPE = "recovery"


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """An ordinary session. Scoped tokens are refused here **by default**.

    T3.16 mints a token whose only purpose is to bind a new way in after a
    recovery code was used. Whitelisting it per endpoint would mean every route
    written from now on inherits it by forgetting to think about it; refusing
    any token that carries a `scope` claim inverts that — a route must ask for
    the scoped dependency on purpose.
    """
    return await _resolve_user(token, db, allow_scope=None)


async def get_recovery_or_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """For the two doors a locked-out user needs: set a password, register a
    passkey. Accepts an ordinary session as well, because someone who still has
    one is doing the same, entirely normal thing."""
    return await _resolve_user(token, db, allow_scope=RECOVERY_SCOPE)


async def _resolve_user(token: str, db: AsyncSession, *, allow_scope: str | None) -> User:
    payload = decode_access_token(token)
    scope = payload.get("scope")
    if scope is not None and scope != allow_scope:
        raise HTTPException(status_code=403, detail="Token is not valid for this action")
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
