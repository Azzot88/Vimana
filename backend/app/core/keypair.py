"""T2.2 — secp256k1 keypair per user (Nostr-compatible).

Two-layer design:
- `generate_keypair() → (nsec_hex, npub_hex)` produces a random Schnorr-signable pair.
- `encrypt_nsec / decrypt_nsec` wrap the private key with AES-256-GCM using
  `NSEC_ENCRYPTION_KEY` from env (**separate from `MESSAGE_ENCRYPTION_KEY`** so
  compromising one doesn't compromise the other).
- `sign_event(payload_json, nsec_hex) → sig_hex` and `verify_event(...)` implement
  NIP-01-style Schnorr sig: `sig = schnorr_sign(sha256(payload), nsec)`.

When user claims self-custody, `nsec_encrypted` is DELETE-ed from DB and
server can no longer sign — client must pre-sign events via NIP-07.
"""
from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache

from coincurve import PrivateKey, PublicKey, PublicKeyXOnly
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_ENV = "NSEC_ENCRYPTION_KEY"
_NONCE_LEN = 12


@lru_cache(maxsize=1)
def _load_key() -> bytes:
    raw = os.getenv(_KEY_ENV, "").strip()
    if not raw:
        raise RuntimeError(
            f"{_KEY_ENV} is not set. Generate with `openssl rand -base64 32`."
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"{_KEY_ENV} is not valid base64: {exc}") from exc
    if len(key) != 32:
        raise RuntimeError(f"{_KEY_ENV} must decode to 32 bytes (got {len(key)}).")
    return key


def reset_key_cache() -> None:
    """For tests that swap the env var mid-run."""
    _load_key.cache_clear()


def generate_keypair() -> tuple[str, str]:
    """Fresh keypair. Returns (nsec_hex, npub_hex) — both 64 hex chars.

    Nostr convention: `npub` is the x-only public key (32 bytes).
    """
    priv = PrivateKey()
    nsec_hex = priv.secret.hex()
    npub_hex = _npub_from_privkey(priv)
    return nsec_hex, npub_hex


def _npub_from_privkey(priv: PrivateKey) -> str:
    """x-only pubkey per BIP-340 / NIP-01."""
    pub = priv.public_key
    # coincurve.PublicKey format returns 33-byte compressed; x-only = last 32 bytes
    compressed = pub.format(compressed=True)
    return compressed[1:].hex()  # drop parity byte


def npub_from_nsec(nsec_hex: str) -> str:
    """Derive npub_hex from nsec_hex — for import path (T2.2 self-custody)."""
    priv = PrivateKey(bytes.fromhex(nsec_hex))
    return _npub_from_privkey(priv)


def encrypt_nsec(nsec_hex: str) -> tuple[bytes, bytes]:
    """Return (nonce, ciphertext) — same shape as core.crypto for symmetry."""
    key = _load_key()
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, nsec_hex.encode("ascii"), None)
    return nonce, ct


def decrypt_nsec(nonce: bytes, ciphertext: bytes) -> str:
    key = _load_key()
    pt = AESGCM(key).decrypt(nonce, ciphertext, None)
    return pt.decode("ascii")


def sign_event(payload_json: str, nsec_hex: str) -> str:
    """Schnorr sign(sha256(payload)) with nsec. Returns 64-byte hex signature.

    `payload_json` should be the canonical serialization of whatever we want to
    make tamper-evident. For Vimana Phase 2 that's the DealVaultMessage /
    DealEvent content (no need for full NIP-01 event envelope at this stage).
    """
    priv = PrivateKey(bytes.fromhex(nsec_hex))
    digest = hashlib.sha256(payload_json.encode("utf-8")).digest()
    sig = priv.sign_schnorr(digest)
    return sig.hex()


def verify_event(payload_json: str, sig_hex: str, npub_hex: str) -> bool:
    """Verify signature against x-only pubkey."""
    try:
        digest = hashlib.sha256(payload_json.encode("utf-8")).digest()
        pub = PublicKeyXOnly(bytes.fromhex(npub_hex))
        return pub.verify(bytes.fromhex(sig_hex), digest)
    except Exception:
        return False
