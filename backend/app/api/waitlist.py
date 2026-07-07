import logging
import os
import re
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_desc
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


class WaitlistOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    source: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


def _admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _admin_chat_ids() -> list[str]:
    raw = os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


async def require_admin_token(x_admin_token: str = Header(default="")):
    expected = os.getenv("ADMIN_API_TOKEN", "")
    if not expected or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=403, detail="Admin token required")


@router.post("", response_model=WaitlistOut, status_code=201)
@limiter.limit("3/minute")
async def join_waitlist(request: Request, body: WaitlistCreate, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    name = (body.name or "").strip() or None
    source = (body.source or "").strip() or None

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email")

    entry = WaitlistEntry(email=email, name=name, source=source)
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
    for chat_id in _admin_chat_ids():
        try:
            send_telegram(chat_id, msg)
        except Exception:
            logger.exception("Failed to send Telegram notification to %s", chat_id)

    return entry


@router.get("", response_model=Page[WaitlistOut], dependencies=[Depends(require_admin_token)])
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
