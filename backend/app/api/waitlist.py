import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.telegram import send_telegram
from app.models.waitlist import WaitlistEntry

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
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Admin token required")


@router.post("", response_model=WaitlistOut, status_code=201)
async def join_waitlist(body: WaitlistCreate, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    name = (body.name or "").strip() or None
    source = (body.source or "").strip() or None

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email")

    existing = await db.execute(select(WaitlistEntry).where(WaitlistEntry.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already on the waitlist")

    entry = WaitlistEntry(email=email, name=name, source=source)
    db.add(entry)
    await db.commit()
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
            pass

    return entry


@router.get("", response_model=list[WaitlistOut], dependencies=[Depends(require_admin_token)])
async def list_waitlist(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WaitlistEntry).order_by(desc(WaitlistEntry.created_at))
    )
    return list(result.scalars().all())
