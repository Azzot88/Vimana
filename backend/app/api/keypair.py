"""T3.12 — service key vs identity.

Until a user takes their own key, `nostr_pubkey` holds a **service key**: the
platform generated it, still holds the nsec, and uses it to encrypt that user's
vault contents and sign their records. It is not shown as "your key" and is
never published outside. Identity begins at `establish`, and always with a
*different* key.

`POST /me/keypair/import` is **gone**. It set `nostr_pubkey` from a bare
`npub_hex` with no proof of possession whatsoever. Once the key is the identity
that is plain impersonation: paste a well-known npub, become that identity.

`export` and `claim` are gone too:

- `claim` promoted the service key to an identity by deleting the server's copy
  of the nsec. That nsec sat on our disks for the account's whole life, so "we
  deleted our copy" is unprovable — an identity built on it is sovereign only
  on the platform's word.
- `export` handed over the service key, which was never the user's to begin
  with.

They outlived `import` by one step: seven test modules used them to obtain a
known nsec and flip users to self-custody. Those tests now either call
`establish` (when they want a self-custody account) or read the service key
straight from the database (when the account must stay custodial) — which is
honest about who can do that: the platform, not the user.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.challenge import ChallengeUnavailable, consume_challenge, issue_challenge
from app.core.challenge import CHALLENGE_TTL_SECONDS
from app.core.database import get_db
from app.core.identity import establish_blockers, rewrap_vault_envelopes
from app.core.identity_proof import PURPOSE_ESTABLISH, verify_proof
from app.core.keypair import decrypt_nsec
from app.core.step_up import StepUpScope, consume as consume_step_up
from app.core.verification import (
    rewrap_container_to_identity,
    verify_container_envelope,
)
from app.models.marketplace import Trip
from app.models.user import User
from app.models.verification import IdentityContainer

router = APIRouter()

_CHALLENGE_SCOPE = "identity:establish"


class KeypairStatus(BaseModel):
    npub: str | None
    # T3.12 — the meaningful pair. `identity_established=False` means the npub
    # above is a service key the platform holds, not the user's identity.
    identity_established: bool
    key_lost: bool
    # DEPRECATED (T3.12) — kept so the existing crypto suite and frontend keep
    # reading. `key_self_custody` is the same bit as `identity_established`;
    # `has_encrypted_nsec` is its inverse for accounts that have any key at all.
    key_self_custody: bool
    has_encrypted_nsec: bool
    model_config = ConfigDict(from_attributes=False)


class ChallengeOut(BaseModel):
    challenge: str
    expires_in: int
    purpose: str


class EstablishBody(BaseModel):
    npub_hex: str
    challenge: str
    created_at: int
    sig: str

    @field_validator("npub_hex")
    @classmethod
    def _hex_64(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("npub_hex must be 64 lowercase hex chars")
        return v

    @field_validator("sig")
    @classmethod
    def _sig_hex(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 128 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("sig must be 128 lowercase hex chars")
        return v


class DeclareLostBody(BaseModel):
    # T3.15 — confirmation now comes from step-up, which every account can
    # produce. The old `password` field is gone: it locked passwordless
    # accounts out of the one irreversible action they are most likely to need.
    step_up_token: str


def _status(user: User) -> KeypairStatus:
    return KeypairStatus(
        npub=user.nostr_pubkey,
        identity_established=user.identity_established,
        key_lost=user.key_lost,
        key_self_custody=user.key_self_custody,
        has_encrypted_nsec=user.nsec_encrypted is not None,
    )


@router.get("/me/keypair/status", response_model=KeypairStatus)
async def keypair_status(current_user: User = Depends(get_current_user)):
    return _status(current_user)


@router.post("/me/identity/challenge", response_model=ChallengeOut)
async def identity_challenge(current_user: User = Depends(get_current_user)):
    """Hand out a one-time nonce to sign. Requesting a new one invalidates the
    previous — a reloaded page must not leave a signable stale nonce around."""
    if current_user.identity_established:
        raise HTTPException(status_code=409, detail="Identity already established")
    try:
        nonce = await issue_challenge(_CHALLENGE_SCOPE, str(current_user.id))
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    return ChallengeOut(
        challenge=nonce,
        expires_in=CHALLENGE_TTL_SECONDS,
        purpose=PURPOSE_ESTABLISH,
    )


@router.post("/me/identity/establish", response_model=KeypairStatus)
async def identity_establish(
    body: EstablishBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Take ownership of the account's identity with a key the platform never saw.

    The server learns only the npub and a signature. Whether the key was
    generated in the browser or came from a NIP-07 extension is invisible here
    — and deliberately so: there is one code path, and it checks the only thing
    that matters, that the caller controls the key.
    """
    if current_user.identity_established:
        raise HTTPException(status_code=409, detail="Identity already established")
    if current_user.key_lost_at is not None:
        raise HTTPException(status_code=403, detail="Account is retired (key lost)")

    # Refuse before touching anything if the transition would strand data.
    blockers = await establish_blockers(db, current_user)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail="Cannot establish identity yet: " + "; ".join(blockers),
        )

    try:
        ok = await consume_challenge(
            _CHALLENGE_SCOPE, str(current_user.id), body.challenge
        )
    except ChallengeUnavailable:
        raise HTTPException(status_code=503, detail="Challenge store unavailable")
    if not ok:
        raise HTTPException(status_code=401, detail="Challenge is unknown or used")

    if not verify_proof(
        body.npub_hex,
        PURPOSE_ESTABLISH,
        body.challenge,
        body.created_at,
        body.sig,
    ):
        raise HTTPException(status_code=401, detail="Invalid proof of key possession")

    taken = await db.execute(
        select(User).where(
            User.nostr_pubkey == body.npub_hex, User.id != current_user.id
        )
    )
    if taken.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This key belongs to another account")

    # Move anything encrypted to the service key across *before* destroying it
    # — this is the only moment both halves exist.
    #
    # Inline, in this request's transaction, rather than the Celery task the
    # task description called for. Two reasons, and the first is decisive:
    #
    # 1. A background task can only start after this request commits, i.e.
    #    after the service key is destroyed. If it then failed, no retry could
    #    ever fix the data — the key needed to read it no longer exists.
    #    Inline, any failure rolls the whole transaction back and the user is
    #    left exactly as they were, still custodial.
    # 2. Postgres gives the atomicity for free: the re-wrapped blobs and the
    #    key swap land in one commit or neither does. A task would need its own
    #    staging, resumption and reconciliation to approximate that.
    #
    # The cost is latency proportional to the number of containers. Acceptable
    # while that number is small (zero in production today); if it ever grows,
    # the answer is to stage the re-wrap *before* the key swap in a separate
    # step, not to move this half behind a queue.
    old_nsec_hex = None
    if current_user.nsec_encrypted is not None and current_user.nsec_nonce is not None:
        old_nsec_hex = decrypt_nsec(
            bytes(current_user.nsec_nonce), bytes(current_user.nsec_encrypted)
        )
    if old_nsec_hex and current_user.nostr_pubkey:
        containers = (
            await db.execute(
                select(IdentityContainer).where(
                    IdentityContainer.owner_id == current_user.id
                )
            )
        ).scalars().all()
        for container in containers:
            rewrap_container_to_identity(
                container,
                old_nsec_hex=old_nsec_hex,
                old_npub_hex=current_user.nostr_pubkey,
                new_npub_hex=body.npub_hex,
            )
            # Prove it before burning the bridge. ECDH is symmetric, so the
            # envelope we just wrote can be opened with the sender key we still
            # hold; the check runs to the plaintext and compares `doc_hash`.
            # A container that survives commit unreadable can never be fixed —
            # the key that could have re-done the wrap is gone.
            if not verify_container_envelope(
                container,
                sender_nsec_hex=old_nsec_hex,
                recipient_npub_hex=body.npub_hex,
            ):
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Re-encryption self-check failed — identity not changed, "
                        "your data is untouched"
                    ),
                )

        # T3.12 pt.2c — same move for e2e vault envelopes. Raises if any of them
        # cannot be proven to round-trip, which rolls this transaction back with
        # the service key still in place.
        try:
            await rewrap_vault_envelopes(
                db,
                current_user,
                old_nsec_hex=old_nsec_hex,
                old_npub_hex=current_user.nostr_pubkey,
                new_npub_hex=body.npub_hex,
            )
        except (ValueError, HTTPException) as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Vault re-encryption self-check failed — identity not "
                    f"changed, your data is untouched ({exc})"
                ),
            )

    # The service key dies here: the platform keeps no copy of anything it can
    # sign or decrypt for this user any more.
    current_user.nostr_pubkey = body.npub_hex
    current_user.nsec_encrypted = None
    current_user.nsec_nonce = None
    current_user.key_self_custody = True
    await db.commit()
    await db.refresh(current_user)

    # T3.12 pt.3 — listings the platform published on this carrier's behalf are
    # signed by the platform key and say `carrier_pubkey: null`. Now that they
    # have one, retract them so they can republish under their own name.
    # kind-30402 is replaceable per (pubkey, d-tag), so an event from a
    # different key does not supersede the platform's — it has to be deleted.
    # Fire-and-forget: a listing that outlives its retraction is stale marketing
    # copy, not evidence, and must not be able to fail the transition.
    published = (
        await db.execute(
            select(Trip).where(
                Trip.carrier_id == current_user.id,
                Trip.nostr_event_id.isnot(None),
            )
        )
    ).scalars().all()
    if published:
        from app.tasks.nostr_publish import delete_trip_from_nostr

        for trip in published:
            try:
                delete_trip_from_nostr.delay(str(trip.id))
            except Exception:  # broker down — the listing simply lingers
                pass

    return _status(current_user)


@router.post("/me/identity/declare-lost", response_model=KeypairStatus)
async def identity_declare_lost(
    body: DeclareLostBody = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark the identity key as gone. One-way.

    Confirmation comes from step-up (T3.15), not from a key proof: the key
    being unavailable is the very thing being declared. Step-up accepts a
    password, a passkey or a Nostr signature, so an account with no password —
    exactly the kind most likely to lose a key — can finally do this. Until
    T3.15 it answered 409 to them.
    """
    if not current_user.identity_established:
        raise HTTPException(
            status_code=409,
            detail="No identity to lose — the platform still holds this account's key",
        )
    if current_user.key_lost_at is not None:
        return _status(current_user)  # idempotent
    await consume_step_up(
        str(current_user.id), StepUpScope.DECLARE_LOST, body.step_up_token
    )

    current_user.key_lost_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)
    return _status(current_user)
