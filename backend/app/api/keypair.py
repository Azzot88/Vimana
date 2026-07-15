"""T2.2 — user's Nostr keypair management (custodial ↔ self-custody).

Flow (per TECHSTATE D10, Variant A + D):
- Register auto-generates keypair (see app.api.auth.register).
- User can `export` → get nsec_hex (re-auth required).
- After export, user may `claim` → server DELETES nsec_encrypted and sets
  `key_self_custody=True`. Server can no longer sign — client must NIP-07 sign.
- Alternatively, user can `import` a foreign nsec/npub → immediately
  self-custody (server never stores foreign nsec).
"""
from pydantic import BaseModel, ConfigDict, field_validator
from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.keypair import decrypt_nsec, encrypt_nsec, npub_from_nsec
from app.core.security import verify_password
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class KeypairStatus(BaseModel):
    npub: str | None
    key_self_custody: bool
    has_encrypted_nsec: bool
    model_config = ConfigDict(from_attributes=False)


class ExportBody(BaseModel):
    password: str  # re-auth confirmation


class ExportResponse(BaseModel):
    nsec_hex: str
    npub_hex: str


class ImportBody(BaseModel):
    nsec_hex: str | None = None  # if provided, npub derived from it
    npub_hex: str | None = None  # otherwise, only npub is stored (read-only tracking)

    @field_validator("nsec_hex")
    @classmethod
    def _hex_64(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("nsec_hex must be 64 lowercase hex chars")
        return v

    @field_validator("npub_hex")
    @classmethod
    def _npub_hex_64(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("npub_hex must be 64 lowercase hex chars")
        return v


@router.get("/me/keypair/status", response_model=KeypairStatus)
async def keypair_status(current_user: User = Depends(get_current_user)):
    return KeypairStatus(
        npub=current_user.nostr_pubkey,
        key_self_custody=current_user.key_self_custody,
        has_encrypted_nsec=current_user.nsec_encrypted is not None,
    )


@router.post("/me/keypair/export", response_model=ExportResponse)
async def keypair_export(
    body: ExportBody = Body(...),
    current_user: User = Depends(get_current_user),
):
    """Export nsec_hex — requires password re-auth. Idempotent (doesn't delete)."""
    if not current_user.password_hash or not verify_password(
        body.password, current_user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid password")
    if current_user.nsec_encrypted is None or current_user.nsec_nonce is None:
        raise HTTPException(
            status_code=404,
            detail="No custodial nsec on this account (already self-custody)",
        )
    nsec_hex = decrypt_nsec(bytes(current_user.nsec_nonce), bytes(current_user.nsec_encrypted))
    return ExportResponse(nsec_hex=nsec_hex, npub_hex=current_user.nostr_pubkey or "")


@router.post("/me/keypair/claim", response_model=KeypairStatus)
async def keypair_claim(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm self-custody. Platform DELETES its copy of nsec."""
    if current_user.key_self_custody:
        # Already self-custody — idempotent
        return KeypairStatus(
            npub=current_user.nostr_pubkey,
            key_self_custody=True,
            has_encrypted_nsec=False,
        )
    current_user.nsec_encrypted = None
    current_user.nsec_nonce = None
    current_user.key_self_custody = True
    await db.commit()
    return KeypairStatus(
        npub=current_user.nostr_pubkey,
        key_self_custody=True,
        has_encrypted_nsec=False,
    )


@router.post("/me/keypair/import", response_model=KeypairStatus)
async def keypair_import(
    body: ImportBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace generated keypair with a user-provided one. NEVER stores foreign nsec.

    Two modes:
    - `nsec_hex` provided → derive npub, set self_custody=True, nsec is NOT stored on server.
    - `npub_hex` only → tracking-only, self_custody=True, no signing possible server-side.
    """
    if body.nsec_hex:
        npub = npub_from_nsec(body.nsec_hex)
    elif body.npub_hex:
        npub = body.npub_hex
    else:
        raise HTTPException(status_code=422, detail="nsec_hex or npub_hex required")

    current_user.nostr_pubkey = npub
    current_user.nsec_encrypted = None
    current_user.nsec_nonce = None
    current_user.key_self_custody = True
    await db.commit()
    return KeypairStatus(
        npub=npub,
        key_self_custody=True,
        has_encrypted_nsec=False,
    )
