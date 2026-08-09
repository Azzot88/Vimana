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
    """Point Telegram at our webhook, carrying the shared secret.

    `secret_token` is the whole reason the endpoint can trust an update: with
    it Telegram sends `X-Telegram-Bot-Api-Secret-Token` on every call, and
    `api/telegram.telegram_webhook` compares it. Registering the webhook
    *without* it while `TELEGRAM_WEBHOOK_SECRET` is set meant every real update
    was rejected with 403 — the bot would look configured and link nobody.
    Found 2026-08-09 while writing the setup instructions, before the bot
    existed to demonstrate it.

    `allowed_updates` narrows the firehose to messages: the linking flow reads
    `/start` and nothing else, and every other update type would be parsed,
    ignored and logged for no purpose.

    Called by: `api/telegram.register_webhook`.
    """
    import os

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if secret:
        payload["secret_token"] = secret
    resp = httpx.post(url, json=payload, timeout=10)
    return resp.json()
