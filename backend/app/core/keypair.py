"""T2.2 — secp256k1 keypair per user (Nostr-compatible).

Two-layer design:
- `generate_keypair() → (nsec_hex, npub_hex)` produces a random Schnorr-signable pair.
- `encrypt_nsec / decrypt_nsec` wrap the private key with AES-256-GCM using
  `NSEC_ENCRYPTION_KEY` from env (**separate from `MESSAGE_ENCRYPTION_KEY`** so
  compromising one doesn't compromise the other).
- `sign_event_id / verify_event_id` sign a precomputed NIP-01 event id (T2.2 pt.2).

The signing pair from T2.2 pt.1 — `sign_event` / `verify_event`, raw
`schnorr(sha256(payload))` — is gone (T_KEYS.1). It was kept "for backward compat
with records signed before the pt.2 refactor"; a full grep found no caller, not
even a test, and no such record exists. What it did keep alive was a second,
non-NIP-01 way to sign, sitting one autocomplete away from the real one.

Ownership of the key is a ladder, not a flag — see `D-KEY-TIERS`. While the
platform holds a copy it can sign for the user; once the copy is deleted
(T3.22) `nsec_encrypted` is NULL and it cannot, so the client signs via NIP-07
or an imported key.
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache

from coincurve import PrivateKey, PublicKeyXOnly
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


def sign_event_id(event_id_hex: str, nsec_hex: str) -> str:
    """T2.2 pt.2 — Schnorr sign a precomputed 32-byte NIP-01 event id."""
    priv = PrivateKey(bytes.fromhex(nsec_hex))
    sig = priv.sign_schnorr(bytes.fromhex(event_id_hex))
    return sig.hex()


def verify_event_id(event_id_hex: str, sig_hex: str, npub_hex: str) -> bool:
    """T2.2 pt.2 — verify Schnorr sig against a NIP-01 event id."""
    try:
        pub = PublicKeyXOnly(bytes.fromhex(npub_hex))
        return pub.verify(bytes.fromhex(sig_hex), bytes.fromhex(event_id_hex))
    except Exception:
        return False
