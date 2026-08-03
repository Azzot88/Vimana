"""T2.3 — Threshold 2-of-3 encryption for DealVault.

Runtime split:

- **Frontend** (`frontend/src/lib/threshold.ts`) generates a per-message
  `session_key`, AES-256-GCM encrypts the plaintext, Shamir-splits(2, 3) the
  key into three shares, and NIP-44-wraps each share (and a per-participant
  session-key "read package") under the target npub.

- **Backend** stores the opaque blob and, on `POST /threshold/disputes/
  {deal_id}/arbiter-reveal`, unwraps the arbiter's share using the platform
  arbiter's server-held nsec (custodial). Arbiter's client combines it with a
  cooperating party's share to reconstruct the session key locally.

We use **NIP-44 v2** (ChaCha20 + HMAC-SHA256 + length padding) so any NIP-07
extension exposing `nip44` can unwrap read-packages client-side without our
having to bundle custom crypto. Author's npub (already stored on the message
via T2.2 pt.2) is the "sender pubkey" for the recipient's NIP-44 decrypt.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid

from coincurve import PrivateKey, PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from fastapi import HTTPException


def _pub_from_xonly(xonly_hex: str) -> PublicKey:
    return PublicKey(bytes.fromhex("02" + xonly_hex))


def nip04_shared_x(priv_hex: str, xonly_pub_hex: str) -> bytes:
    """ECDH x-coordinate, 32 bytes. NIP-44 runs it through HKDF (see below);
    NIP-04 used it as an AES key directly, which is one of the reasons it went."""
    priv = PrivateKey(bytes.fromhex(priv_hex))
    pub = _pub_from_xonly(xonly_pub_hex)
    shared_point = pub.multiply(priv.secret)
    return shared_point.format(compressed=True)[1:33]

def envelope_parts(entry, default_sender_pubkey: str | None) -> tuple[str, str | None]:
    """Split a stored envelope into (ciphertext, sender_pubkey).

    Two shapes exist (T3.12 pt.2c):

    - legacy `"<ct>"` — the sender was always the message author, so the caller
      supplies it as `default_sender_pubkey`;
    - `{"ct": "<ct>", "sender_pubkey": "<hex>"}` — carries its own sender.

    The second shape exists because the envelope is ECDH-addressed: re-addressing an envelope to
    a new key requires the *sender's* private key. When a user takes their own
    identity, the platform re-wraps their envelopes using the retiring service
    key as sender — which only works if the reader can be told that is who to
    complete the exchange with. With sender pinned to the message author, that
    re-wrap was impossible and such accounts could not migrate at all.
    """
    if isinstance(entry, dict):
        return entry.get("ct", ""), entry.get("sender_pubkey")
    return entry, default_sender_pubkey


def make_envelope(ciphertext: str, sender_pubkey: str) -> dict:
    return {"ct": ciphertext, "sender_pubkey": sender_pubkey}


def get_arbiter_user_id() -> uuid.UUID | None:
    """Platform-arbiter selection via `ARBITER_USER_ID` env.

    Returns None if unset — endpoints then respond 503 so ops can bootstrap the
    arbiter user after migration without breaking non-arbiter flows.
    """
    raw = os.getenv("ARBITER_USER_ID", "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


class E2EPayload:
    """Structural validator for the client-supplied e2e blob. Keeping this here
    (instead of Pydantic) lets us reuse it from multiple routers without a
    circular schema import.

    Expected shape:
    ```
    {
      "ciphertext": "<b64 AES-GCM ct>",
      "nonce":      "<b64 12-byte AES-GCM nonce>",
      "wrapped_shares": {
        "sender":  "<NIP-44 payload>",
        "carrier": "<NIP-44 payload>",
        "arbiter": "<NIP-44 payload>"
      },
      "read_packages": {
        "sender":  "<NIP-44 payload of session_key>",
        "carrier": "<NIP-44 payload of session_key>"
      }
    }
    ```
    """

    __slots__ = ("ciphertext_b64", "nonce_b64", "wrapped_shares", "read_packages")

    def __init__(self, raw: dict):
        if not isinstance(raw, dict):
            raise HTTPException(status_code=422, detail="e2e_payload must be an object")
        self.ciphertext_b64 = raw.get("ciphertext")
        self.nonce_b64 = raw.get("nonce")
        self.wrapped_shares = raw.get("wrapped_shares") or {}
        self.read_packages = raw.get("read_packages") or {}
        if not isinstance(self.ciphertext_b64, str) or not isinstance(
            self.nonce_b64, str
        ):
            raise HTTPException(
                status_code=422,
                detail="e2e_payload.ciphertext and .nonce must be base64 strings",
            )
        if not isinstance(self.wrapped_shares, dict) or set(
            self.wrapped_shares.keys()
        ) != {"sender", "carrier", "arbiter"}:
            raise HTTPException(
                status_code=422,
                detail="e2e_payload.wrapped_shares must contain {sender, carrier, arbiter}",
            )
        if not isinstance(self.read_packages, dict) or not (
            {"sender", "carrier"} <= set(self.read_packages.keys())
        ):
            raise HTTPException(
                status_code=422,
                detail="e2e_payload.read_packages must contain sender and carrier",
            )
        for role, val in self.wrapped_shares.items():
            # T_KEYS.1 — this used to look for `?iv=`, the NIP-04 marker. The
            # check is deliberately shallow: a NIP-44 payload is base64 whose
            # first byte is the version, and that is all the server can judge
            # without the key. Verifying more would mean pretending to validate
            # something only the recipient can open.
            ok = isinstance(val, str)
            if ok:
                try:
                    raw = base64.b64decode(val, validate=True)
                    ok = len(raw) >= 97 and raw[0] == NIP44_VERSION
                except (ValueError, TypeError):
                    ok = False
            if not ok:
                raise HTTPException(
                    status_code=422,
                    detail=f"wrapped_shares.{role} must be a NIP-44 payload string",
                )

    def to_blob(self) -> tuple[bytes, bytes, dict]:
        try:
            ct = base64.b64decode(self.ciphertext_b64)
            nonce = base64.b64decode(self.nonce_b64)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Bad base64: {exc}")
        combined = {
            "wrapped_shares": self.wrapped_shares,
            "read_packages": self.read_packages,
        }
        return ct, nonce, combined


# ─────────────────────────────────────────────────────────────
# T_KEYS.1 — NIP-44 v2 (замена NIP-04)
# ─────────────────────────────────────────────────────────────
#
# NIP-04, which this replaced, is deprecated *in the Nostr spec itself*, for the
# reason that matters here: AES-256-CBC with a raw ECDH x-coordinate and no MAC.
# Unauthenticated. A stored envelope can be modified and the reader has no way
# to notice — in a vault built on "changes are detectable", that is the wrong
# primitive to be holding the session keys.
#
# NIP-44 v2 fixes exactly that:
#   - ChaCha20 instead of AES-CBC (stream, no padding oracle)
#   - HMAC-SHA256 over nonce||ciphertext — authentication, which NIP-04 lacks
#   - length padding, so the size of a message stops leaking its content
#   - HKDF over the ECDH output instead of using the raw x-coordinate as a key
#
# Migration is single-shot, no compatibility branch. Measured on prod
# 2026-08-02: zero E2E messages, zero identity containers, therefore zero
# NIP-04 envelopes in existence. There is nothing to re-encrypt and nothing to
# stay compatible with — see `TASKS.md` `T_KEYS.1`.

NIP44_VERSION = 2


def nip44_conversation_key(priv_hex: str, xonly_pub_hex: str) -> bytes:
    """HKDF-extract over the ECDH x-coordinate, salt `nip44-v2`.

    NIP-04 used the x-coordinate directly as an AES key. It is a curve point
    coordinate, not uniformly random, and reusing it per conversation means one
    key for every message ever exchanged between two identities. HKDF fixes the
    distribution; the per-message nonce below fixes the reuse.
    """
    shared_x = nip04_shared_x(priv_hex, xonly_pub_hex)
    return hmac.new(b"nip44-v2", shared_x, hashlib.sha256).digest()


def _nip44_message_keys(conversation_key: bytes, nonce: bytes) -> tuple[bytes, bytes, bytes]:
    """HKDF-expand to (chacha_key, chacha_nonce, hmac_key) = 32 + 12 + 32."""
    okm = b""
    block = b""
    counter = 1
    while len(okm) < 76:
        block = hmac.new(
            conversation_key, block + nonce + bytes([counter]), hashlib.sha256
        ).digest()
        okm += block
        counter += 1
    return okm[0:32], okm[32:44], okm[44:76]


def _nip44_padded_len(unpadded: int) -> int:
    """Padding schedule from the NIP-44 spec.

    The point is that ciphertext length stops being a fingerprint of the
    plaintext: everything up to 32 bytes looks identical, and beyond that
    lengths collapse into buckets. Without it, "yes"/"no" are distinguishable
    by size alone, which for a vault of negotiations is a real leak.
    """
    if unpadded <= 32:
        return 32
    next_power = 1 << (unpadded - 1).bit_length()
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * ((unpadded - 1) // chunk + 1)


def _nip44_pad(plaintext: bytes) -> bytes:
    if not 1 <= len(plaintext) <= 65535:
        raise HTTPException(status_code=422, detail="NIP-44 plaintext length out of range")
    prefixed = len(plaintext).to_bytes(2, "big") + plaintext
    return prefixed + b"\x00" * (_nip44_padded_len(len(plaintext)) + 2 - len(prefixed))


def _nip44_unpad(padded: bytes) -> bytes:
    if len(padded) < 2:
        raise HTTPException(status_code=422, detail="NIP-44 padding truncated")
    declared = int.from_bytes(padded[:2], "big")
    plaintext = padded[2 : 2 + declared]
    # Both checks matter: a wrong declared length must not silently yield a
    # shorter message, and the total must match what the schedule would have
    # produced — otherwise the padding itself becomes a place to hide bytes.
    if declared < 1 or len(plaintext) != declared or len(padded) != _nip44_padded_len(declared) + 2:
        raise HTTPException(status_code=422, detail="NIP-44 padding invalid")
    return plaintext


def _chacha20(key: bytes, nonce12: bytes, data: bytes) -> bytes:
    """ChaCha20 keystream with counter 0.

    `cryptography` takes a 16-byte nonce laid out as counter(4, little-endian)
    followed by the 12-byte nonce, so the leading zeros are the counter the NIP
    specifies — not padding.
    """
    cipher = Cipher(algorithms.ChaCha20(key, b"\x00" * 4 + nonce12), mode=None)
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


def nip44_encrypt(plaintext: bytes, sender_priv_hex: str, recipient_xonly_pub_hex: str) -> str:
    """NIP-44 v2 payload, base64: version || nonce(32) || ciphertext || mac(32)."""
    conversation_key = nip44_conversation_key(sender_priv_hex, recipient_xonly_pub_hex)
    nonce = os.urandom(32)
    chacha_key, chacha_nonce, hmac_key = _nip44_message_keys(conversation_key, nonce)
    ciphertext = _chacha20(chacha_key, chacha_nonce, _nip44_pad(plaintext))
    mac = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()
    return base64.b64encode(bytes([NIP44_VERSION]) + nonce + ciphertext + mac).decode("ascii")


def nip44_decrypt(payload_b64: str, recipient_priv_hex: str, sender_xonly_pub_hex: str) -> bytes:
    """Inverse of `nip44_encrypt`. 422 on any structural or authentication failure.

    The MAC is checked **before** decryption and in constant time. This is the
    whole reason for the migration: NIP-04 had nothing to check, so a modified
    envelope decrypted to garbage and the caller had no way to tell that from a
    wrong key.
    """
    if payload_b64.startswith("#"):
        raise HTTPException(status_code=422, detail="NIP-44: unsupported version")
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"NIP-44 base64: {exc}") from exc
    if len(raw) < 1 + 32 + 32 + 32 or raw[0] != NIP44_VERSION:
        raise HTTPException(status_code=422, detail="NIP-44: bad version or length")

    nonce, ciphertext, mac = raw[1:33], raw[33:-32], raw[-32:]
    conversation_key = nip44_conversation_key(recipient_priv_hex, sender_xonly_pub_hex)
    chacha_key, chacha_nonce, hmac_key = _nip44_message_keys(conversation_key, nonce)
    expected = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise HTTPException(status_code=422, detail="NIP-44: authentication failed")
    return _nip44_unpad(_chacha20(chacha_key, chacha_nonce, ciphertext))
