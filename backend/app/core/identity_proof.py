"""T3.12 pt.2 — proof that the caller controls a Nostr key.

The server never sees a private key. It hands out a challenge, the client signs
a canonical NIP-01 event over it, and the server recomputes the event id and
verifies the signature against the claimed npub.

Why a proof is mandatory, not a nicety: the endpoint this feeds writes
`users.nostr_pubkey`, and under `D-KEY-IS-IDENTITY` that column *is* the
user's identity. Accepting a bare npub — which the old `POST /me/keypair/import`
did (`app/api/keypair.py`, removed in this task) — let anyone paste a
well-known npub and claim that identity as their own.

The event shape is deliberately independent of the request URL. Strict NIP-98
binds a proof to an absolute URL, which drags deploy-time origin config into
signature verification and breaks the moment dev and prod differ. Binding to an
explicit `purpose` string gives the same protection against cross-use — a proof
minted for `establish` cannot be replayed at login — without that fragility.
T3.13 reuses this module with its own purpose.
"""
from __future__ import annotations

import time

from app.core.keypair import verify_event_id
from app.core.signing import compute_event_id

# NIP-98 "HTTP Auth" kind. Reused rather than inventing a private kind so an
# external Nostr client could produce these too.
PROOF_KIND = 27235
CLOCK_SKEW_SEC = 60

PURPOSE_ESTABLISH = "vimana:identity:establish"
# T3.13 — separate purposes so a proof cannot be carried between flows. The
# purpose is *inside* the signed payload, so a signature collected for one of
# these is worthless for the others even with a live challenge.
PURPOSE_LOGIN = "vimana:identity:login"
PURPOSE_SIGNUP = "vimana:identity:signup"


def build_proof_event(
    npub_hex: str, purpose: str, challenge: str, created_at: int
) -> dict:
    """Canonical event both sides hash. Field order and tag shape are part of
    the contract — changing either invalidates every proof in flight."""
    return {
        "pubkey": npub_hex,
        "created_at": created_at,
        "kind": PROOF_KIND,
        "tags": [["challenge", challenge], ["purpose", purpose]],
        "content": purpose,
    }


def proof_event_id(
    npub_hex: str, purpose: str, challenge: str, created_at: int
) -> str:
    event = build_proof_event(npub_hex, purpose, challenge, created_at)
    return compute_event_id(
        event["pubkey"],
        event["created_at"],
        event["kind"],
        event["tags"],
        event["content"],
    )


def verify_proof(
    npub_hex: str,
    purpose: str,
    challenge: str,
    created_at: int,
    sig_hex: str,
    *,
    now: int | None = None,
) -> bool:
    """True only if `sig_hex` is a valid signature by `npub_hex` over the
    canonical event for exactly this purpose and challenge.

    The timestamp window is checked here as well as the challenge TTL: a
    freshly-signed event with a wildly wrong `created_at` means the client's
    clock — or the caller — is not what it claims to be.
    """
    now = now if now is not None else int(time.time())
    if abs(created_at - now) > CLOCK_SKEW_SEC:
        return False
    event_id = proof_event_id(npub_hex, purpose, challenge, created_at)
    return verify_event_id(event_id, sig_hex, npub_hex)
