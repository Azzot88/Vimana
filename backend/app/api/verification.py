"""T2.1 MVP — Peer Identity Verification endpoints.

Flow:
1. Participant creates request (`POST /deals/{id}/verification`) — target_role=sender|carrier.
2. Target responds via `/respond` — 3-option UX (later / decline / upload).
   - sender's `declined` = badge on profile.
   - carrier's `declined_polite` = neutral system-message, no consequences.
3. `upload` path opens `/submit-document` — creates encrypted `IdentityContainer`
   + auto-level `VerificationBadge`.
4. Requester can ask for extra docs via `/request-additional` or escalate to
   arbiter via `/escalate` (creates Dispute; deal → disputed).

Self-verification (outside a deal) via `POST /me/verification/self-upload`.
Public read via `GET /users/{id}/verifications` (no document contents).
Revoke via `POST /verifications/{badge_id}/revoke`.

**MVP compromises** (documented for T2.3 follow-up):
- OCR = skip (accept `doc_type`, `doc_country` from body).
- Sanctions = stub returns `clean`.
- Container encryption = custodial-only (self-custody → 422).
"""
import hashlib
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, is_superuser
from app.core.database import get_db
from app.core.permissions import Permission, has_perm, require_perm
from app.core.verification import (
    ContainerEncryptionError,
    check_sanctions_stub,
    decrypt_container,
    encrypt_container,
    refresh_highest_level,
    sha256_hex,
)
from app.models.deal import Deal, DealStatus, Dispute, DisputeStatus
from app.models.user import User
from app.models.verification import (
    IdentityContainer,
    OwnerRole,
    VerificationBadge,
    VerificationLevel,
    VerificationRequest,
    VerificationRequestStatus,
    VerificationSource,
    VerificationTargetRole,
)
from app.schemas.verification import (
    UserVerificationSummary,
    VerificationBadgeOut,
    VerificationEscalateBody,
    VerificationRequestCreate,
    VerificationRequestOut,
    VerificationRespondBody,
)

router = APIRouter()

MAX_DOC_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 64 * 1024
PEER_REVOKE_WINDOW = timedelta(days=30)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


async def _get_deal_as_participant(
    deal_id: uuid.UUID, user: User, db: AsyncSession
) -> Deal:
    deal = await db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if user.id not in (deal.sender_id, deal.carrier_id):
        raise HTTPException(status_code=403, detail="Not a deal participant")
    return deal


async def _get_request(
    deal_id: uuid.UUID, req_id: uuid.UUID, db: AsyncSession
) -> VerificationRequest:
    req = await db.get(VerificationRequest, req_id)
    if not req or req.deal_id != deal_id:
        raise HTTPException(status_code=404, detail="Verification request not found")
    return req


def _target_user_id(deal: Deal, req: VerificationRequest) -> uuid.UUID:
    return (
        deal.sender_id
        if req.target_role == VerificationTargetRole.sender
        else deal.carrier_id
    )


async def _create_badge_and_refresh(
    db: AsyncSession,
    *,
    subject_id: uuid.UUID,
    level: VerificationLevel,
    source: VerificationSource,
    container_ref_id: uuid.UUID | None,
    verified_by_id: uuid.UUID | None,
    in_deal_id: uuid.UUID | None,
    expires_at: datetime | None,
) -> VerificationBadge:
    badge = VerificationBadge(
        subject_id=subject_id,
        level=level,
        source=source,
        container_ref_id=container_ref_id,
        verified_by_id=verified_by_id,
        in_deal_id=in_deal_id,
        expires_at=expires_at,
    )
    db.add(badge)
    await db.flush()
    await refresh_highest_level(subject_id, db)
    return badge


# ─────────────────────────────────────────────────────────────
# Request lifecycle
# ─────────────────────────────────────────────────────────────


@router.post(
    "/deals/{deal_id}/verification",
    response_model=VerificationRequestOut,
    status_code=201,
)
async def create_request(
    deal_id: uuid.UUID,
    body: VerificationRequestCreate,
    current_user: User = Depends(require_perm(Permission.IDENTITY_REQUEST)),
    db: AsyncSession = Depends(get_db),
):
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    try:
        target_role = VerificationTargetRole(body.target_role)
    except ValueError:
        raise HTTPException(status_code=422, detail="target_role must be sender|carrier")

    # Requester must be the OTHER party (can't request from self)
    my_role = "sender" if current_user.id == deal.sender_id else "carrier"
    if target_role.value == my_role:
        raise HTTPException(
            status_code=422, detail="Requester and target must be different roles"
        )

    req = VerificationRequest(
        deal_id=deal_id,
        requested_by_id=current_user.id,
        target_role=target_role,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


@router.post(
    "/deals/{deal_id}/verification/{req_id}/respond",
    response_model=VerificationRequestOut,
)
async def respond(
    deal_id: uuid.UUID,
    req_id: uuid.UUID,
    body: VerificationRespondBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    req = await _get_request(deal_id, req_id, db)
    if current_user.id != _target_user_id(deal, req):
        raise HTTPException(status_code=403, detail="You are not the target of this request")
    if req.status != VerificationRequestStatus.pending:
        raise HTTPException(status_code=409, detail="Request already resolved")

    action = body.action
    now = datetime.now(timezone.utc)

    if action == "later_in_person":
        req.status = VerificationRequestStatus.later_in_person
    elif action == "declined":
        # Only sender-target can outright decline (carries badge on profile)
        if req.target_role != VerificationTargetRole.sender:
            raise HTTPException(
                status_code=422,
                detail="'declined' is only valid when target is sender; carriers use 'declined_polite'",
            )
        req.status = VerificationRequestStatus.declined
        req.resolved_at = now
    elif action == "declined_polite":
        # Only carrier-target — no consequences, neutral system-message flow
        if req.target_role != VerificationTargetRole.carrier:
            raise HTTPException(
                status_code=422,
                detail="'declined_polite' is only valid when target is carrier",
            )
        req.status = VerificationRequestStatus.declined_polite
        req.resolved_at = now
    elif action == "upload":
        # Client will then call /submit-document; keep status pending until doc arrives.
        # We accept a no-op response to signal intent.
        pass
    else:
        raise HTTPException(status_code=422, detail=f"Unknown action: {action}")

    await db.commit()
    await db.refresh(req)
    return req


@router.post(
    "/deals/{deal_id}/verification/{req_id}/submit-document",
    response_model=VerificationBadgeOut,
    status_code=201,
)
async def submit_document(
    deal_id: uuid.UUID,
    req_id: uuid.UUID,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    doc_country: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    req = await _get_request(deal_id, req_id, db)
    if current_user.id != _target_user_id(deal, req):
        raise HTTPException(status_code=403, detail="You are not the target of this request")

    doc_bytes, detected_mime = await _read_upload(file)
    container = await _make_container(
        db, owner=current_user, blob=doc_bytes, doc_type=doc_type, doc_country=doc_country
    )
    badge = await _create_badge_and_refresh(
        db,
        subject_id=current_user.id,
        level=VerificationLevel.auto,
        source=VerificationSource.auto_ocr,
        container_ref_id=container.id,
        verified_by_id=None,
        in_deal_id=deal_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    req.status = VerificationRequestStatus.verified
    req.resolved_at = datetime.now(timezone.utc)

    # T3.9 (D-DVLT-PROTOCOL) — identity data lives in BOTH vaults: the
    # canonical encrypted container above (owner-only) and a full copy inside
    # the deal (participant-visible attachment), linked through the chain by
    # a shared doc_hash. All of it commits atomically with the badge.
    await _copy_document_into_vault(
        db,
        deal_id=deal_id,
        actor=current_user,
        doc_bytes=doc_bytes,
        mime=detected_mime,
        container=container,
        badge_id=badge.id,
    )

    await db.commit()
    await db.refresh(badge)
    return badge


@router.post(
    "/deals/{deal_id}/verification/{req_id}/request-additional",
    response_model=VerificationRequestOut,
    status_code=201,
)
async def request_additional(
    deal_id: uuid.UUID,
    req_id: uuid.UUID,
    current_user: User = Depends(require_perm(Permission.IDENTITY_REQUEST)),
    db: AsyncSession = Depends(get_db),
):
    """Requester (not target) asks for one more document. Creates a new request."""
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    existing = await _get_request(deal_id, req_id, db)
    if current_user.id == _target_user_id(deal, existing):
        raise HTTPException(
            status_code=403, detail="The target can't request additional documents from themselves"
        )
    follow_up = VerificationRequest(
        deal_id=deal_id,
        requested_by_id=current_user.id,
        target_role=existing.target_role,
    )
    db.add(follow_up)
    await db.commit()
    await db.refresh(follow_up)
    return follow_up


@router.post(
    "/deals/{deal_id}/verification/{req_id}/escalate",
    response_model=VerificationRequestOut,
)
async def escalate(
    deal_id: uuid.UUID,
    req_id: uuid.UUID,
    body: VerificationEscalateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Dispute (T1.23) with identity_fraud tag, mark request escalated."""
    deal = await _get_deal_as_participant(deal_id, current_user, db)
    req = await _get_request(deal_id, req_id, db)
    # Both parties may escalate — sender if they suspect they were declined unfairly,
    # or carrier if they see a fake document.
    existing_dispute = (
        await db.execute(select(Dispute).where(Dispute.deal_id == deal_id))
    ).scalar_one_or_none()
    if existing_dispute is None:
        dispute = Dispute(
            deal_id=deal_id,
            opened_by=current_user.id,
            reason=f"identity_fraud: {body.reason[:200]}",
            status=DisputeStatus.open,
        )
        db.add(dispute)
        deal.status = DealStatus.disputed
    req.status = VerificationRequestStatus.escalated
    req.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(req)
    return req


# ─────────────────────────────────────────────────────────────
# Self-upload (no deal)
# ─────────────────────────────────────────────────────────────


@router.post(
    "/me/verification/self-upload",
    response_model=VerificationBadgeOut,
    status_code=201,
)
async def self_upload(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    doc_country: str = Form(...),
    current_user: User = Depends(require_perm(Permission.IDENTITY_SELF_UPLOAD)),
    db: AsyncSession = Depends(get_db),
):
    doc_bytes, _ = await _read_upload(file)
    container = await _make_container(
        db, owner=current_user, blob=doc_bytes, doc_type=doc_type, doc_country=doc_country
    )
    badge = await _create_badge_and_refresh(
        db,
        subject_id=current_user.id,
        level=VerificationLevel.auto,
        source=VerificationSource.auto_ocr,
        container_ref_id=container.id,
        verified_by_id=None,
        in_deal_id=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    await db.commit()
    await db.refresh(badge)
    return badge


# ─────────────────────────────────────────────────────────────
# Public read + revoke
# ─────────────────────────────────────────────────────────────


@router.get(
    "/deals/{deal_id}/verification-requests",
    response_model=list[VerificationRequestOut],
)
async def list_deal_requests(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Both participants can see all VerificationRequests scoped to their deal."""
    await _get_deal_as_participant(deal_id, current_user, db)
    rows = (
        await db.execute(
            select(VerificationRequest)
            .where(VerificationRequest.deal_id == deal_id)
            .order_by(VerificationRequest.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.get(
    "/users/{user_id}/verifications", response_model=UserVerificationSummary
)
async def get_user_verifications(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    rows = (
        await db.execute(
            select(VerificationBadge)
            .where(VerificationBadge.subject_id == user_id)
            .order_by(VerificationBadge.verified_at.desc())
        )
    ).scalars().all()
    active = [b for b in rows if b.revoked_at is None]
    counts = {"auto": 0, "peer": 0, "kyc": 0}
    for b in active:
        counts[b.level.value] = counts.get(b.level.value, 0) + 1
    return UserVerificationSummary(
        subject_id=user_id,
        highest_level=user.highest_verification_level,
        active_counts=counts,
        badges=[VerificationBadgeOut.model_validate(b) for b in rows],
    )


@router.post("/verifications/{badge_id}/revoke", response_model=VerificationBadgeOut)
async def revoke_badge(
    badge_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    badge = await db.get(VerificationBadge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    if badge.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Already revoked")

    # Arbiter/superuser can revoke any badge, anytime.
    if has_perm(current_user, Permission.VERIFICATION_REVOKE_ANY):
        pass
    # Verifier can revoke their own peer badge within PEER_REVOKE_WINDOW (30 days).
    elif badge.verified_by_id == current_user.id and badge.level == VerificationLevel.peer:
        if datetime.now(timezone.utc) - badge.verified_at > PEER_REVOKE_WINDOW:
            raise HTTPException(
                status_code=403,
                detail="Peer revoke window (30 days) expired — escalate to arbiter",
            )
    # Subject can revoke their own self-uploaded auto badge (opt out).
    elif badge.subject_id == current_user.id and badge.source == VerificationSource.auto_ocr:
        pass
    else:
        raise HTTPException(status_code=403, detail="You can't revoke this badge")

    badge.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    await refresh_highest_level(badge.subject_id, db)
    await db.commit()
    await db.refresh(badge)
    return badge


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    """Returns `(bytes, detected_mime)` — the MIME comes from signature
    sniffing (T3.8), never from the client's Content-Type header."""
    total = 0
    hasher = hashlib.sha256()
    buf = io.BytesIO()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_DOC_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {MAX_DOC_UPLOAD_SIZE // 1024 // 1024} MB",
            )
        hasher.update(chunk)
        buf.write(chunk)
    data = buf.getvalue()

    # T3.8 — identity documents had no content validation at all. The declared
    # MIME is not even looked at here: the real type is sniffed from the bytes
    # (photo or PDF), images must fully decode. Runs before encryption, so
    # dirt never reaches an IdentityContainer.
    from app.core.file_validation import FileValidationError, validate_document

    # Sniffing plus a full decode is CPU work; off the event loop (T_PERF.1).
    try:
        detected_mime = await run_in_threadpool(validate_document, data)
    except FileValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Document failed content validation: {exc.reason}",
        )
    return data, detected_mime


async def _make_container(
    db: AsyncSession,
    *,
    owner: User,
    blob: bytes,
    doc_type: str,
    doc_country: str,
) -> IdentityContainer:
    try:
        nonce, ct = encrypt_container(owner, blob)
    except ContainerEncryptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    container = IdentityContainer(
        owner_id=owner.id,
        owner_role=OwnerRole.both,
        blob_encrypted=ct,
        blob_nonce=nonce,
        doc_hash=sha256_hex(blob),
        doc_country=doc_country[:2].upper() if doc_country else None,
        doc_type=doc_type[:32] if doc_type else None,
        sanctions_check_status=check_sanctions_stub(None, doc_country),
    )
    db.add(container)
    await db.flush()
    return container


async def _copy_document_into_vault(
    db: AsyncSession,
    *,
    deal_id: uuid.UUID,
    actor: User,
    doc_bytes: bytes,
    mime: str,
    container: "IdentityContainer",
    badge_id: uuid.UUID,
) -> None:
    """T3.9 — mirror a just-verified identity document into the deal vault.

    Creates, in the caller's transaction:
    - a system chat message ("identity document verified…"),
    - an `identity_doc` Attachment with the plaintext copy in R2
      (participant-visible; the canonical container stays owner-encrypted),
    - three chain entries: `message_added`, `file_added`, `identity_ref`.

    `identity_ref.doc_hash` == `Attachment.file_hash` == `IdentityContainer
    .doc_hash` — the triple match is what `verify_content` later re-checks,
    so a swapped copy is detectable even though the chain itself is intact.
    """
    from app.api.dealvault import MIME_TO_EXT
    from app.core.deal_chain import SealedError, append_deal_event, content_hash_of
    from app.core.signing import sign_vault_message
    from app.core.storage import upload_file
    from app.models.deal import Attachment, AttachmentKind, DealEventType, DealVaultMessage

    msg = DealVaultMessage(
        deal_id=deal_id,
        sender_id=actor.id,
        text="🪪 Identity document verified and added to the vault",
        is_system=True,
    )
    sign_vault_message(msg, actor)
    db.add(msg)
    await db.flush()

    ext = MIME_TO_EXT.get(mime, "")
    r2_key = f"deals/{deal_id}/identity/{uuid.uuid4().hex}{ext}"
    # Blocking PUT — off the event loop (T_PERF.1).
    await run_in_threadpool(upload_file, doc_bytes, r2_key, mime)
    attachment = Attachment(
        message_id=msg.id,
        r2_key=r2_key,
        file_hash=container.doc_hash,  # sha256 of the same plaintext bytes
        kind=AttachmentKind.identity_doc,
    )
    db.add(attachment)
    await db.flush()

    try:
        await append_deal_event(
            db,
            deal_id=deal_id,
            event_type=DealEventType.message_added,
            actor_id=actor.id,
            payload={
                "message_id": str(msg.id),
                "content_hash": content_hash_of(msg.text_ciphertext, msg.text_nonce),
                "msg_event_id": msg.nostr_event_id,
                "is_e2e": False,
            },
            author=actor,
        )
        await append_deal_event(
            db,
            deal_id=deal_id,
            event_type=DealEventType.file_added,
            actor_id=actor.id,
            payload={
                "attachment_id": str(attachment.id),
                "message_id": str(msg.id),
                "file_hash": attachment.file_hash,
                "kind": AttachmentKind.identity_doc.value,
                "size_bytes": len(doc_bytes),
                "mime": mime,
            },
            author=actor,
        )
        await append_deal_event(
            db,
            deal_id=deal_id,
            event_type=DealEventType.identity_ref,
            actor_id=actor.id,
            payload={
                "container_id": str(container.id),
                "attachment_id": str(attachment.id),
                "badge_id": str(badge_id),
                "doc_hash": container.doc_hash,
                "doc_type": container.doc_type,
                "doc_country": container.doc_country,
            },
            author=actor,
        )
    except SealedError:
        raise HTTPException(status_code=409, detail="Deal vault is sealed")
