import logging
import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
from app.core.permissions import Permission, require_perm
from app.core.rate_limit import limiter
from app.core.telegram import send_telegram
from app.models.waitlist import WaitlistEntry

logger = logging.getLogger(__name__)

router = APIRouter()

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class WaitlistCreate(BaseModel):
    email: str
    name: str | None = None
    source: str | None = None
    # T_UX.9 — the landing's language, so the confirmation is written in it.
    # The T_UX.7 note about a frozen body covers the three fields above; this
    # one is additive and no reader of the older shape breaks.
    locale: str | None = None


class WaitlistOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    source: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


def _admin_chat_ids() -> list[str]:
    raw = os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


@router.post("", response_model=WaitlistOut, status_code=201)
@limiter.limit("3/minute")
async def join_waitlist(request: Request, body: WaitlistCreate, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    name = (body.name or "").strip() or None
    source = (body.source or "").strip() or None

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email")

    locale = (body.locale or "").strip().lower()[:5] or None
    entry = WaitlistEntry(email=email, name=name, source=source, locale=locale)
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Already on the waitlist")
    await db.refresh(entry)

    msg = f"Vimana · Waitlist +1\n{email}"
    if name:
        msg += f"\n{name}"
    if source:
        msg += f"\nsource: {source}"
    chat_ids = _admin_chat_ids()
    for chat_id in chat_ids:
        try:
            send_telegram(chat_id, msg)
        except Exception:
            logger.exception("Failed to send Telegram notification to %s", chat_id)
    if not chat_ids:
        # Until a bot exists this is the only trace a signup leaves in the logs.
        # The loop above says nothing when the list is empty, and `send_telegram`
        # says nothing when the token is missing — between them a new entry
        # could arrive in total silence, which is how three of them did.
        logger.info("waitlist signup %s (no ADMIN_TELEGRAM_CHAT_IDS configured)", email)

    # T_UX.8 — the letters go to a worker: `send_email` is synchronous smtplib,
    # and holding this async endpoint for two SMTP round-trips would make a
    # stranger wait on a form for our mail server.
    from app.tasks.notifications import send_waitlist_emails

    try:
        send_waitlist_emails.delay(str(entry.id))
    except Exception:
        # Broker unreachable — the row is saved and `confirmation_sent_at` is
        # still NULL, so the backfill task will pick this person up later.
        logger.exception("Failed to queue waitlist emails for %s", email)

    return entry


@router.get(
    "",
    response_model=Page[WaitlistOut],
    dependencies=[Depends(require_perm(Permission.WAITLIST_READ))],
)
async def list_waitlist(
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    base = select(WaitlistEntry)
    items, next_cursor = await paginate_desc(
        db, base, WaitlistEntry, after, clamp_limit(limit)
    )
    return Page(items=items, next_cursor=next_cursor)
