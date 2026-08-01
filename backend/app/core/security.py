import hashlib
import os
import secrets
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


# T3.16 — recovery codes. Alphabet drops 0/O/1/l/I: these get written on paper
# and typed back by a person who has just lost their phone, and that is the
# worst possible moment to discover that a character is ambiguous.
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
RECOVERY_CODE_LENGTH = 12
RECOVERY_CODE_COUNT = 10


def generate_recovery_code() -> str:
    """One code, grouped in fours for reading aloud and copying by hand."""
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
    return "-".join(raw[i : i + 4] for i in range(0, RECOVERY_CODE_LENGTH, 4))


def hash_recovery_code(code: str) -> str:
    """SHA-256 of the normalised code — deliberately **not** bcrypt.

    bcrypt is slow on purpose because passwords are low-entropy and a leaked
    hash must survive a dictionary. A recovery code is 12 characters from a
    31-symbol alphabet — about 59 bits, chosen by `secrets`, never reused and
    never typed by a human twice. There is no dictionary to survive.

    Speed is what makes the endpoint correct rather than merely convenient: a
    fast digest is looked up by equality (one indexed query), whereas bcrypt
    would force verifying the attempt against every unused code of that account
    in turn — ten deliberate slowdowns per guess, which is a denial-of-service
    lever pointed at ourselves. This is the same reasoning under which API keys
    are stored as fast digests and passwords are not.
    """
    return hashlib.sha256(normalise_recovery_code(code).encode("ascii")).hexdigest()


def normalise_recovery_code(code: str) -> str:
    """What the user typed → what we hash. Case and dashes are presentation:
    someone copying from paper will get one or the other wrong, and refusing
    them teaches nothing about security."""
    return "".join(ch for ch in (code or "").upper() if ch in RECOVERY_ALPHABET)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    scope: str | None = None,
) -> str:
    """Signs a JWT with a random `jti` so it can be individually revoked
    (T_UX.3 pt.4a — Redis blacklist), and an `iat` so a whole generation of
    tokens can be retired at once (T3.15 — `users.sessions_valid_from`).

    The two mechanisms answer different questions. `jti` revokes *this* token,
    which is what logout needs. `iat` retires every token older than a moment,
    which is what changing a password needs: the point is to evict a session
    whose identifier we never had.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta if expires_delta is not None else timedelta(days=_DEFAULT_EXPIRE_DAYS)
    )
    payload = {
        "sub": subject,
        "exp": expire,
        # T3.16 — a token with a scope is NOT a session. `get_current_user`
        # refuses anything carrying this claim, so a new scope cannot silently
        # inherit access to every endpoint that predates it: opting in is done
        # per route, by asking for a different dependency.
        **({"scope": scope} if scope else {}),
        # Sub-second on purpose, and passed as a number rather than a datetime:
        # PyJWT truncates datetimes to whole seconds, and whole seconds leave a
        # window where a token minted in the same second as a retirement
        # survives it. RFC 7519 allows a non-integer NumericDate.
        "iat": now.timestamp(),
        "jti": uuid.uuid4().hex,
    }
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
