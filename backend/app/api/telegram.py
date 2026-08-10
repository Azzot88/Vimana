import logging
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

logger = logging.getLogger(__name__)

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
        # Bytes, not str: `compare_digest` refuses non-ASCII `str` with a
        # TypeError, so a header containing any such character produced a 500
        # instead of a 403 — an unauthenticated caller could make the endpoint
        # error at will. Found by the contract fuzzer (T_TEST.4) the first time
        # the secret was actually set in an environment. Encoding makes the
        # comparison total, and the timing property is unchanged.
        x_telegram_bot_api_secret_token.encode("utf-8", "surrogatepass"),
        expected.encode("utf-8", "surrogatepass"),
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    msg = update.message
    if not msg:
        return {"ok": "no message"}

    chat_id = str(msg.get("chat", {}).get("id", ""))
    text: str = msg.get("text", "")
    # Telegram tells us the client's language. Used only for the two replies
    # sent before we know whose account this is — once linked, the account's own
    # `locale` wins, because that is what the person chose on the site.
    hint = (msg.get("from", {}) or {}).get("language_code")

    from app.tasks.notifications import send_telegram_chat

    def reply(kind: str, locale: str | None) -> None:
        """Every branch answers. Silence was the whole complaint: pressing Start
        did the work and looked like nothing happened, and an expired link was
        indistinguishable from a broken bot."""
        if not chat_id:
            return
        try:
            send_telegram_chat.delay(chat_id, kind, locale)
        except Exception:
            logger.exception("could not queue telegram reply to %s", chat_id)

    if text.startswith("/start "):
        token = text.split(" ", 1)[1].strip()
        result = await db.execute(select(User).where(User.telegram_link_token == token))
        user = result.scalar_one_or_none()
        if user:
            user.telegram_chat_id = chat_id
            user.telegram_link_token = None
            user.notify_telegram = True
            await db.commit()
            reply("linked", user.locale)
        else:
            reply("stale", hint)
    else:
        reply("hello", hint)

    return {"ok": "processed"}


@router.post("/disconnect")
async def disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """T_UX.13 — turning the switch off unlinks, it does not just mute.

    Owner's decision 2026-08-09: there is no "linked but silent" state. The
    switch *is* the connection, so off means the chat is forgotten — otherwise
    the profile keeps a chat id nobody can see and nobody asked to keep, and the
    only way to get rid of it is a database query.

    Idempotent: an account that was never linked gets the same answer, because
    "make sure this is not connected" is the request either way.

    Called by: ProfilePage's Telegram switch.
    """
    current_user.telegram_chat_id = None
    current_user.telegram_link_token = None
    current_user.notify_telegram = False
    await db.commit()
    return {"connected": False}


@router.post("/set_webhook")
async def register_webhook(
    _: User = Depends(require_perm(Permission.TELEGRAM_MANAGE)),
) -> dict[str, Any]:
    """Point Telegram at *our* webhook. Superuser only. Takes no input.

    Two holes closed here, both found the hard way.

    It used to require nothing but a session: any signed-in account could
    re-point the bot at a server of their choosing, and Telegram would deliver
    every update — including the `/start` tokens that link accounts — to a
    stranger. Tightened with `TELEGRAM_MANAGE`.

    **And it used to take the URL as a parameter.** `test_contract_fuzz` walks
    every endpoint in the OpenAPI schema as a superuser, so on a server where
    the bot is configured the fuzzer called this with a generated URL and
    `set_webhook` dutifully forwarded it to Telegram. On 2026-08-09 a test run
    unset the production webhook that way: `getWebhookInfo` came back with
    `"url": ""`, linking stopped, and nothing in the app looked wrong. A test
    suite that can break production is not a testing problem, it is this
    endpoint's problem — so the URL is now derived, and there is no input left
    to generate. The worst a fuzz run can now do is re-register the correct
    address.

    Called by: the admin by hand after changing `TELEGRAM_WEBHOOK_SECRET` —
    the secret only travels with a registration, so the two change together.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    base = os.getenv("VIMANA_PUBLIC_URL", "https://vimana.dealvault.club").rstrip("/")
    return set_webhook(f"{base}/api/telegram/webhook")
