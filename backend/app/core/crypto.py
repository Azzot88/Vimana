"""AES-256-GCM at-rest encryption for message text (T1.21).

Server-side key from `MESSAGE_ENCRYPTION_KEY` env (base64-encoded 32 bytes).
This is intentionally NOT end-to-end — server can decrypt. E2E with threshold
decryption comes in T2.3 once Nostr keypairs are wired to users. This layer
still protects against DB dumps, backups, and read-only DB admins.
"""
import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_ENV = "MESSAGE_ENCRYPTION_KEY"
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
        raise RuntimeError(
            f"{_KEY_ENV} must decode to 32 bytes (got {len(key)})."
        )
    return key


def encrypt(plaintext: str) -> tuple[bytes, bytes]:
    """Return (nonce, ciphertext_with_tag) for AES-256-GCM."""
    key = _load_key()
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce, ct


def decrypt(nonce: bytes, ciphertext: bytes) -> str:
    key = _load_key()
    pt = AESGCM(key).decrypt(nonce, ciphertext, None)
    return pt.decode("utf-8")


def reset_key_cache() -> None:
    """For tests that swap the env var mid-run."""
    _load_key.cache_clear()
