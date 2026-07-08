"""Toggle `is_arbiter` for a user by email.

Usage (inside backend container):
    python scripts/make_arbiter.py user@example.com          # promote
    python scripts/make_arbiter.py user@example.com --off    # demote

Meant as a backup path for User Zero. Normal flow — POST /api/admin/users/{id}/promote-arbiter.
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User


async def main(email: str, off: bool) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email.strip().lower()))
        user = result.scalar_one_or_none()
        if not user:
            print(f"User not found: {email}")
            return 1
        user.is_arbiter = not off
        await db.commit()
        state = "OFF" if off else "ON"
        print(f"{email}: is_arbiter = {state}")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    email = sys.argv[1]
    off = "--off" in sys.argv
    sys.exit(asyncio.run(main(email, off)))
