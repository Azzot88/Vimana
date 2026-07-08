"""User Zero — идемпотентная промоция при старте приложения.

nyxter@dealvault.club — единственный владелец платформы. При каждом старте
backend проверяет, что этот аккаунт (если существует) имеет `is_superuser=True`.
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
    if user and not user.is_superuser:
        user.is_superuser = True
        await db.commit()
        logger.info("Promoted %s to superuser (User Zero)", USER_ZERO_EMAIL)
