import hashlib
import io
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.address import AddressNotSetError, format_address_message
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_asc
from app.core.rate_limit import limiter
import base64

from app.core.signing import sign_vault_message
from app.core.storage import get_presigned_url, upload_file
from app.core.threshold import E2EPayload
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
    # For e2e messages the client needs raw ciphertext + own read_package;
    # `text` remains None because server can't decrypt. `wrapped_shares` is NOT
    # surfaced here — arbiter's share is exposed only via the dispute endpoint.
    ciphertext_b64 = None
    nonce_b64 = None
    read_packages = None
    if msg.is_e2e:
        if msg.text_ciphertext is not None:
            ciphertext_b64 = base64.b64encode(bytes(msg.text_ciphertext)).decode("ascii")
        if msg.text_nonce is not None:
            nonce_b64 = base64.b64encode(bytes(msg.text_nonce)).decode("ascii")
        read_packages = msg.read_packages
    return MessageOut(
        id=msg.id,
        deal_id=msg.deal_id,
        sender_id=msg.sender_id,
        text=msg.text,
        is_system=msg.is_system,
        nostr_sig=msg.nostr_sig,
        nostr_event_id=msg.nostr_event_id,
        nostr_created_at=msg.nostr_created_at,
        nostr_pubkey=msg.nostr_pubkey,
        is_e2e=msg.is_e2e,
        ciphertext_b64=ciphertext_b64,
        nonce_b64=nonce_b64,
        read_packages=read_packages,
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

    if body.e2e_payload is not None:
        if body.text is not None:
            raise HTTPException(
                status_code=422,
                detail="e2e_payload and text are mutually exclusive",
            )
        payload = E2EPayload(body.e2e_payload)
        ct, nonce, combined = payload.to_blob()
        msg = DealVaultMessage(
            deal_id=deal_id,
            sender_id=current_user.id,
            is_system=body.is_system,
            is_e2e=True,
        )
        msg.text_ciphertext = ct
        msg.text_nonce = nonce
        msg.wrapped_shares = combined["wrapped_shares"]
        msg.read_packages = combined["read_packages"]
    else:
        msg = DealVaultMessage(
            deal_id=deal_id,
            sender_id=current_user.id,
            text=body.text,
            is_system=body.is_system,
        )
    sign_vault_message(msg, current_user, body.nostr_sig, body.nostr_created_at)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return _build_message_out(msg)


@router.post(
    "/{deal_id}/dealvault/messages/share-address",
    response_model=MessageOut,
    status_code=201,
)
@limiter.limit("5/hour")
async def share_address(
    deal_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T1.26 — share user's receiving address into the DealVault chat as a
    system-message. Body-less; server reads current user's profile."""
    await _get_deal_as_participant(deal_id, current_user, db)
    try:
        text = format_address_message(current_user)
    except AddressNotSetError:
        raise HTTPException(
            status_code=422,
            detail="Receiving address not set — fill it in your profile first",
        )
    msg = DealVaultMessage(
        deal_id=deal_id,
        sender_id=current_user.id,
        text=text,
        is_system=True,
    )
    sign_vault_message(msg, current_user)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return MessageOut(
        id=msg.id,
        deal_id=msg.deal_id,
        sender_id=msg.sender_id,
        text=msg.text,
        is_system=msg.is_system,
        nostr_sig=msg.nostr_sig,
        nostr_event_id=msg.nostr_event_id,
        nostr_created_at=msg.nostr_created_at,
        nostr_pubkey=msg.nostr_pubkey,
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
