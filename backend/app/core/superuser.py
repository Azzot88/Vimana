"""User Zero — идемпотентная промоция при старте приложения.

nyxter@dealvault.club — единственный владелец платформы. При каждом старте
backend проверяет, что этот аккаунт (если существует) имеет `role='superuser'`.
Никакой другой email не может получить superuser через этот механизм.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

USER_ZERO_EMAIL = "nyxter@dealvault.club"

logger = logging.getLogger(__name__)


async def ensure_user_zero(db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == USER_ZERO_EMAIL))
    user = result.scalar_one_or_none()
    if user and "superuser" not in (user.roles or []):
        # T3.42 — roles add up, so this appends rather than replaces: User Zero
        # who also took an arbiter role keeps it. Assignment would have silently
        # revoked it on the next restart, which is exactly the failure the
        # single-column model produced everywhere else.
        user.roles = [*(user.roles or []), "superuser"]
        # No `RoleGrant` row: this role is not granted by anybody. It comes from
        # the address in the environment, and a journal entry would describe a
        # decision that was never made. `core/roles.py` refuses to offer or
        # revoke `superuser` for the same reason.
        await db.commit()
        logger.info("Promoted %s to superuser (User Zero)", USER_ZERO_EMAIL)
