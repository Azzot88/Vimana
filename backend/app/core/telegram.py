import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_telegram(chat_id: str, text: str) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception:
        logger.exception("Telegram sendMessage failed for chat_id=%s", chat_id)


def set_webhook(webhook_url: str) -> dict:
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    resp = httpx.post(url, json={"url": webhook_url}, timeout=10)
    return resp.json()
