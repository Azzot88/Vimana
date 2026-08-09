import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.permissions import Permission, require_perm
from app.core.database import get_db
from app.core.telegram import set_webhook
from app.models.user import User

router = APIRouter()


class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None


@router.get("/connect")
async def get_connect_link(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    token = secrets.token_urlsafe(32)
    current_user.telegram_link_token = token
    await db.commit()
    link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}"
    return {"link": link, "already_connected": bool(current_user.telegram_chat_id)}


@router.post("/webhook")
async def telegram_webhook(
    update: TelegramUpdate,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict[str, str]:
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if expected and not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    msg = update.message
    if not msg:
        return {"ok": "no message"}

    chat_id = str(msg.get("chat", {}).get("id", ""))
    text: str = msg.get("text", "")

    if text.startswith("/start "):
        token = text.split(" ", 1)[1].strip()
        result = await db.execute(select(User).where(User.telegram_link_token == token))
        user = result.scalar_one_or_none()
        if user:
            user.telegram_chat_id = chat_id
            user.telegram_link_token = None
            user.notify_telegram = True
            await db.commit()

    return {"ok": "processed"}


@router.post("/set_webhook")
async def register_webhook(
    webhook_url: str,
    _: User = Depends(require_perm(Permission.TELEGRAM_MANAGE)),
) -> dict[str, Any]:
    """Register the webhook. Superuser only.

    It used to require nothing but a session. Any signed-in account could
    re-point the bot at a server of their choosing — Telegram would then
    deliver every update, including the `/start` tokens that link accounts, to
    a stranger, and linking here would simply stop working. Tightened
    2026-08-09 alongside the `secret_token` fix; the two together are what
    makes the webhook trustworthy in either direction.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    result = set_webhook(webhook_url)
    return result
