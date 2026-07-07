import hashlib
import io
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_asc
from app.core.storage import get_presigned_url, upload_file
from app.models.deal import Attachment, AttachmentKind, Deal, DealVaultMessage
from app.models.user import User
from app.schemas.dealvault import AttachmentOut, MessageCreate, MessageOut

router = APIRouter()

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 64 * 1024  # 64 KB

_PHOTO_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_DOC_MIME = _PHOTO_MIME | {"application/pdf"}

ALLOWED_MIME_BY_KIND: dict[AttachmentKind, set[str]] = {
    AttachmentKind.handoff_photo: _PHOTO_MIME,
    AttachmentKind.receipt_photo: _PHOTO_MIME,
    AttachmentKind.doc: _DOC_MIME,
    AttachmentKind.payment_receipt: _DOC_MIME,
}

MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "application/pdf": ".pdf",
}


async def _get_deal_as_participant(
    deal_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Deal:
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if current_user.id not in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Not a deal participant")
    return deal


def _build_message_out(msg: DealVaultMessage) -> MessageOut:
    attachments_out = []
    for a in msg.attachments:
        attachments_out.append(
            AttachmentOut(
                id=a.id,
                message_id=a.message_id,
                r2_key=a.r2_key,
                file_hash=a.file_hash,
                ipfs_cid=a.ipfs_cid,
                kind=a.kind.value,
                url=get_presigned_url(a.r2_key),
                created_at=a.created_at,
            )
        )
    return MessageOut(
        id=msg.id,
        deal_id=msg.deal_id,
        sender_id=msg.sender_id,
        text=msg.text,
        is_system=msg.is_system,
        attachments=attachments_out,
        created_at=msg.created_at,
    )


@router.get("/{deal_id}/dealvault", response_model=Page[MessageOut])
async def list_messages(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    await _get_deal_as_participant(deal_id, current_user, db)

    base = (
        select(DealVaultMessage)
        .where(DealVaultMessage.deal_id == deal_id)
        .options(selectinload(DealVaultMessage.attachments))
    )
    items, next_cursor = await paginate_asc(
        db, base, DealVaultMessage, after, clamp_limit(limit)
    )
    return Page(items=[_build_message_out(m) for m in items], next_cursor=next_cursor)


@router.post("/{deal_id}/dealvault/messages", response_model=MessageOut, status_code=201)
async def create_message(
    deal_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_deal_as_participant(deal_id, current_user, db)

    msg = DealVaultMessage(
        deal_id=deal_id,
        sender_id=current_user.id,
        text=body.text,
        is_system=body.is_system,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return MessageOut(
        id=msg.id,
        deal_id=msg.deal_id,
        sender_id=msg.sender_id,
        text=msg.text,
        is_system=msg.is_system,
        attachments=[],
        created_at=msg.created_at,
    )


@router.post(
    "/{deal_id}/dealvault/messages/{message_id}/attachments",
    response_model=AttachmentOut,
    status_code=201,
)
async def upload_attachment(
    deal_id: uuid.UUID,
    message_id: uuid.UUID,
    request: Request,
    file: UploadFile,
    kind: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_deal_as_participant(deal_id, current_user, db)

    msg = await db.get(DealVaultMessage, message_id)
    if not msg or msg.deal_id != deal_id:
        raise HTTPException(status_code=404, detail="Message not found in this deal")

    try:
        attachment_kind = AttachmentKind(kind)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid kind: {kind}")

    # Early rejection via Content-Length before reading bytes
    declared_length = request.headers.get("content-length")
    if declared_length and int(declared_length) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {MAX_UPLOAD_SIZE // 1024 // 1024} MB",
        )

    content_type = (file.content_type or "").lower()
    allowed = ALLOWED_MIME_BY_KIND.get(attachment_kind, set())
    if content_type not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"MIME '{content_type}' not allowed for kind '{kind}'",
        )

    # Streaming SHA-256 + size limit while reading chunks
    hasher = hashlib.sha256()
    total = 0
    buffer = io.BytesIO()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {MAX_UPLOAD_SIZE // 1024 // 1024} MB",
            )
        hasher.update(chunk)
        buffer.write(chunk)

    file_hash = hasher.hexdigest()
    # Extension derived from MIME (whitelisted), never from user-supplied filename
    ext = MIME_TO_EXT.get(content_type, "")
    r2_key = f"deals/{deal_id}/attachments/{uuid.uuid4().hex}{ext}"

    upload_file(buffer.getvalue(), r2_key, content_type)

    attachment = Attachment(
        message_id=message_id,
        r2_key=r2_key,
        file_hash=file_hash,
        kind=attachment_kind,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return AttachmentOut(
        id=attachment.id,
        message_id=attachment.message_id,
        r2_key=attachment.r2_key,
        file_hash=attachment.file_hash,
        ipfs_cid=attachment.ipfs_cid,
        kind=attachment.kind.value,
        url=get_presigned_url(attachment.r2_key),
        created_at=attachment.created_at,
    )
