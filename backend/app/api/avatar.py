"""T_UX.4 B follow-up — user avatar upload backed by the same R2 bucket
that stores DealVault attachments."""
from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.avatar_url import me_out_with_avatar
from app.core.storage import upload_file
from app.models.user import User
from app.schemas.user import MeOut

router = APIRouter()

_MAX_AVATAR_SIZE = 3 * 1024 * 1024  # 3 MB — plenty for a headshot
_CHUNK = 64 * 1024
_ALLOWED_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@router.post("/me/avatar", response_model=MeOut)
async def upload_avatar(
    request: Request,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    declared = request.headers.get("content-length")
    if declared and int(declared) > _MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {_MAX_AVATAR_SIZE // 1024 // 1024} MB",
        )

    ct = (file.content_type or "").lower()
    if ct not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"MIME '{ct}' not allowed. Use jpeg/png/webp.",
        )

    total = 0
    buf = io.BytesIO()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_AVATAR_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {_MAX_AVATAR_SIZE // 1024 // 1024} MB",
            )
        buf.write(chunk)

    ext = _ALLOWED_MIME[ct]
    key = f"avatars/{current_user.id}/{uuid.uuid4().hex}.{ext}"
    upload_file(buf.getvalue(), key, ct)

    current_user.avatar_key = key
    await db.commit()
    await db.refresh(current_user)
    return me_out_with_avatar(current_user)


@router.delete("/me/avatar", response_model=MeOut)
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletion is soft — we forget the key. The R2 object is orphaned; a
    Celery janitor is a follow-up."""
    current_user.avatar_key = None
    await db.commit()
    await db.refresh(current_user)
    return me_out_with_avatar(current_user)
