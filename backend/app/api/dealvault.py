import hashlib
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.address import (
    AddressNotSetError,
    format_address_message,
    resolve_share_address,
)
from app.core.database import get_db
from app.core.pagination import Page, clamp_limit, paginate_asc
from app.core.rate_limit import limiter
import base64

from app.core.deal_chain import SealedError, append_deal_event, content_hash_of
from app.core.file_validation import FileValidationError, validate_upload
from app.core.keypair import decrypt_nsec
from app.core.signing import sign_vault_message
from app.core.storage import get_presigned_url, presign_ttl_for_kind, upload_file
from app.core.threshold import E2EPayload, envelope_parts, nip44_decrypt
from app.core.cards import CardKind, role_of, spec_for
from app.models.deal import (
    Attachment, AttachmentKind, CardState, Deal, DealEventType, DealVaultMessage,
)
from app.models.user import User
from app.schemas.dealvault import AttachmentOut, CardAckIn, MessageCreate, MessageOut

logger = logging.getLogger(__name__)

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
    if current_user.id in (deal.sender_id, deal.carrier_id):
        return deal
    # T3.3 — active recipients also have access.
    from app.models.deal import DealParticipant as DP
    row = (
        await db.execute(
            select(DP).where(
                DP.deal_id == deal_id,
                DP.user_id == current_user.id,
                DP.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=403, detail="Not a deal participant")
    return deal


def _ensure_not_sealed(deal: Deal) -> None:
    """T3.7 — a sealed vault takes no new content. Early check for a clean 409;
    `append_deal_event` re-checks under the advisory lock as the race-safe
    backstop (see `_chain_message`)."""
    if deal.sealed_at is not None:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")


async def _chain_message(db, msg: DealVaultMessage, actor: User) -> None:
    """T3.7 — chain a freshly-flushed vault message in the same transaction.

    The chain entry carries `content_hash` over the stored bytes (works for e2e
    without decryption) and the message's own `nostr_event_id`, binding the
    author's signature into the chain. Deleting or editing the message row is
    detectable from then on (`verify_content`).
    """
    try:
        await append_deal_event(
            db,
            deal_id=msg.deal_id,
            event_type=DealEventType.message_added,
            actor_id=actor.id,
            payload={
                "message_id": str(msg.id),
                "content_hash": content_hash_of(msg.text_ciphertext, msg.text_nonce),
                "msg_event_id": msg.nostr_event_id,
                "is_e2e": msg.is_e2e,
            },
            author=actor,
        )
    except SealedError:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")


def _build_message_out(
    msg: DealVaultMessage, *, skip_attachments: bool = False
) -> MessageOut:
    """Serialize a vault message.

    `skip_attachments=True` — for freshly-created rows where the caller knows
    there are no attachments yet. Prevents `attachments is not available due to
    lazy='raise'` when the row hasn't been loaded via `selectinload`.
    """
    attachments_out: list[AttachmentOut] = []
    if not skip_attachments:
        for a in msg.attachments:
            attachments_out.append(
                AttachmentOut(
                    id=a.id,
                    message_id=a.message_id,
                    r2_key=a.r2_key,
                    file_hash=a.file_hash,
                    ipfs_cid=a.ipfs_cid,
                    kind=a.kind.value,
                    url=get_presigned_url(
                        a.r2_key, expires=presign_ttl_for_kind(a.kind.value)
                    ),
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
        card_kind=msg.card_kind,
        card_payload=msg.card_payload,
        card_state=msg.card_state.value if msg.card_state else None,
        requires_ack_by=msg.requires_ack_by.value if msg.requires_ack_by else None,
        acked_by_id=msg.acked_by_id,
        acked_at=msg.acked_at,
        supersedes_id=msg.supersedes_id,
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
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    _ensure_not_sealed(deal)

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
    # T3.7 — flush so the message has an id, then chain it in the same
    # transaction: message and its chain entry commit or roll back together.
    await db.flush()
    await _chain_message(db, msg, current_user)
    await db.commit()
    await db.refresh(msg)

    return _build_message_out(msg, skip_attachments=True)


class ShareAddressBody(BaseModel):
    address_id: uuid.UUID | None = None


@router.post(
    "/{deal_id}/dealvault/messages/share-address",
    response_model=MessageOut,
    status_code=201,
)
@limiter.limit("5/hour")
async def share_address(
    deal_id: uuid.UUID,
    request: Request,
    body: ShareAddressBody = ShareAddressBody(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T1.26 / T_UX.4 A — share a receiving address into the DealVault chat
    as a system-message. `address_id` picks a specific one; omit to use the
    default; falls back to legacy `User.receiving_*` for un-migrated users."""
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    _ensure_not_sealed(deal)
    try:
        view = await resolve_share_address(db, current_user, body.address_id)
        text = format_address_message(view)
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
        # T3.34 — the type lives here now. The text keeps the address so the
        # card renders exactly as before; only recognition moved off the prefix.
        card_kind=CardKind.address_shared.value,
    )
    sign_vault_message(msg, current_user)
    db.add(msg)
    await db.flush()
    await _chain_message(db, msg, current_user)
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
        card_kind=msg.card_kind,
        card_payload=msg.card_payload,
        card_state=msg.card_state.value if msg.card_state else None,
        requires_ack_by=msg.requires_ack_by.value if msg.requires_ack_by else None,
        acked_by_id=msg.acked_by_id,
        acked_at=msg.acked_at,
        supersedes_id=msg.supersedes_id,
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
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    _ensure_not_sealed(deal)

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

    # T3.8 — validate the bytes against the declared type BEFORE the R2 write:
    # signature whitelist + full image decode. Metadata only in the log.
    # Decode runs in the threadpool (T_PERF.1) — see `api/avatar.py` for why.
    try:
        scan_status = await run_in_threadpool(
            validate_upload, buffer.getvalue(), content_type
        )
    except FileValidationError as exc:
        logger.warning(
            "upload rejected: deal=%s user=%s kind=%s declared=%s size=%d reason=%s",
            deal_id, current_user.id, kind, content_type, total, exc.reason,
        )
        raise HTTPException(
            status_code=422,
            detail=f"File content failed validation: {exc.reason}",
        )

    # Extension derived from MIME (whitelisted), never from user-supplied filename
    ext = MIME_TO_EXT.get(content_type, "")
    r2_key = f"deals/{deal_id}/attachments/{uuid.uuid4().hex}{ext}"

    # Blocking PUT — off the event loop (T_PERF.1). Attachments here are the
    # largest files the product accepts, so this is the worst place to hold it.
    await run_in_threadpool(upload_file, buffer.getvalue(), r2_key, content_type)

    attachment = Attachment(
        message_id=message_id,
        r2_key=r2_key,
        file_hash=file_hash,
        kind=attachment_kind,
        # T3.8 — what we know about these bytes, recorded with them. `pending`
        # means the scanner was unreachable or absent and the file is queued;
        # it never means "safe" (owner's decision 2026-08-02).
        scan_status=scan_status,
        scanned_at=datetime.now(timezone.utc) if scan_status != "pending" else None,
    )
    db.add(attachment)
    # T3.7 — chain the file in the same transaction as its row. `file_hash`
    # was already streamed above; the chain entry pins it so a swapped or
    # deleted attachment row is detectable (`verify_content`).
    await db.flush()
    try:
        await append_deal_event(
            db,
            deal_id=deal_id,
            event_type=DealEventType.file_added,
            actor_id=current_user.id,
            payload={
                "attachment_id": str(attachment.id),
                "message_id": str(message_id),
                "file_hash": file_hash,
                "kind": attachment_kind.value,
                "size_bytes": total,
                "mime": content_type,
            },
            author=current_user,
        )
    except SealedError:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")
    await db.commit()
    await db.refresh(attachment)

    return AttachmentOut(
        id=attachment.id,
        message_id=attachment.message_id,
        r2_key=attachment.r2_key,
        file_hash=attachment.file_hash,
        ipfs_cid=attachment.ipfs_cid,
        kind=attachment.kind.value,
        url=get_presigned_url(
            attachment.r2_key, expires=presign_ttl_for_kind(attachment.kind.value)
        ),
        created_at=attachment.created_at,
    )


@router.post("/{deal_id}/dealvault/messages/{message_id}/decrypt-for-me")
async def decrypt_message_for_me(
    deal_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.3 — server-mediated decrypt for participants who don't hold their
    own keys client-side (recipients invited via T3.3).

    Trade-off: sender / carrier retain full E2E (they decrypt via NIP-07);
    recipient trusts the platform to relay plaintext into their browser via
    HTTPS. Server sees plaintext for milliseconds and does not store it.

    Custodial callers (sender/carrier who haven't claimed self-custody) can
    also use this endpoint as a convenience — same trust model.
    """
    await _get_deal_as_participant(deal_id, current_user, db)
    msg = await db.get(DealVaultMessage, message_id)
    if msg is None or msg.deal_id != deal_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if not msg.is_e2e:
        raise HTTPException(status_code=400, detail="Message is not e2e; use standard read")
    if not msg.read_packages:
        raise HTTPException(status_code=422, detail="Message has no read_packages")

    # Locate a read_package addressed to the caller. Keys can be role-based
    # ("sender"/"carrier") or recipient-scoped ("recipient_<uuid>").
    from app.models.deal import DealParticipant as DP
    deal = await db.get(Deal, deal_id)
    read_pkg: str | None = None
    if deal.sender_id == current_user.id:
        read_pkg = msg.read_packages.get("sender")
    elif deal.carrier_id == current_user.id:
        read_pkg = msg.read_packages.get("carrier")
    else:
        # Recipient path.
        row = (
            await db.execute(
                select(DP).where(
                    DP.deal_id == deal_id,
                    DP.user_id == current_user.id,
                    DP.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            read_pkg = msg.read_packages.get(f"recipient_{row.user_id}")
    if read_pkg is None:
        raise HTTPException(
            status_code=403,
            detail="No read package for you on this message",
        )
    if current_user.nsec_encrypted is None or current_user.nsec_nonce is None:
        raise HTTPException(
            status_code=422,
            detail="Server-mediated decrypt requires custodial nsec (self-custody users decrypt client-side)",
        )
    # T3.12 pt.2c — a re-wrapped package names its own sender; a legacy one was
    # always addressed from the message author.
    ciphertext, sender_pubkey = envelope_parts(read_pkg, msg.nostr_pubkey)
    if not sender_pubkey:
        raise HTTPException(
            status_code=422,
            detail="Read package has no sender pubkey — cannot complete NIP-04 exchange",
        )

    caller_nsec = decrypt_nsec(bytes(current_user.nsec_nonce), bytes(current_user.nsec_encrypted))
    session_key = nip44_decrypt(ciphertext, caller_nsec, sender_pubkey)

    # Now AES-GCM decrypt the ciphertext with the recovered session_key.
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ct = bytes(msg.text_ciphertext or b"")
    nonce = bytes(msg.text_nonce or b"")
    try:
        plaintext = AESGCM(session_key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"AES-GCM decrypt failed: {exc}")

    return {"message_id": str(message_id), "text": plaintext}


@router.post(
    "/{deal_id}/dealvault/messages/{message_id}/ack",
    response_model=MessageOut,
)
async def ack_card(
    deal_id: uuid.UUID,
    message_id: uuid.UUID,
    body: CardAckIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """T3.34 — answer a card that is waiting on you.

    The role check is the whole point of the endpoint. Hiding the button in the
    UI is a convenience; refusing the write here is the rule (§6.9.5 п.6).
    """
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    _ensure_not_sealed(deal)

    if body.decision not in ("accepted", "declined"):
        raise HTTPException(status_code=422, detail="decision must be accepted or declined")

    msg = (
        await db.execute(
            select(DealVaultMessage).where(
                DealVaultMessage.id == message_id,
                DealVaultMessage.deal_id == deal_id,
            )
        )
    ).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.card_kind is None:
        raise HTTPException(status_code=422, detail="Message is not a card")
    if spec_for(msg.card_kind) is None:
        # A row written by a version that knew a kind this one does not. Refusing
        # beats guessing at what the card meant.
        raise HTTPException(status_code=422, detail="Unknown card type")
    if msg.requires_ack_by is None:
        raise HTTPException(status_code=422, detail="This card does not await an answer")
    if msg.card_state is not CardState.pending:
        # Answering twice is not an error the user can fix by retrying, so it
        # gets a conflict rather than a validation complaint.
        raise HTTPException(status_code=409, detail="Card is no longer pending")

    if role_of(deal, current_user.id) is not msg.requires_ack_by:
        raise HTTPException(
            status_code=403, detail="This card awaits the other side"
        )

    msg.card_state = (
        CardState.accepted if body.decision == "accepted" else CardState.declined
    )
    msg.acked_by_id = current_user.id
    msg.acked_at = datetime.now(timezone.utc)
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
        card_kind=msg.card_kind,
        card_payload=msg.card_payload,
        card_state=msg.card_state.value if msg.card_state else None,
        requires_ack_by=msg.requires_ack_by.value if msg.requires_ack_by else None,
        acked_by_id=msg.acked_by_id,
        acked_at=msg.acked_at,
        supersedes_id=msg.supersedes_id,
        attachments=[],
        created_at=msg.created_at,
    )
