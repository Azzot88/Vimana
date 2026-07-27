"""T2.3 — Threshold 2-of-3 encryption for DealVault.

Runtime split:

- **Frontend** (`frontend/src/lib/threshold.ts`) generates a per-message
  `session_key`, AES-256-GCM encrypts the plaintext, Shamir-splits(2, 3) the
  key into three shares, and NIP-04-wraps each share (and a per-participant
  session-key "read package") under the target npub.

- **Backend** stores the opaque blob and, on `POST /threshold/disputes/
  {deal_id}/arbiter-reveal`, unwraps the arbiter's share using the platform
  arbiter's server-held nsec (custodial). Arbiter's client combines it with a
  cooperating party's share to reconstruct the session key locally.

We use **NIP-04** (kind-4 DM format: AES-256-CBC + raw-x ECDH) so any NIP-07
extension (Alby, nos2x, ...) can unwrap read-packages client-side without our
having to bundle custom crypto. Author's npub (already stored on the message
via T2.2 pt.2) is the "sender pubkey" for the recipient's NIP-04 decrypt.
"""
from __future__ import annotations

import base64
import os
import uuid

from coincurve import PrivateKey, PublicKey
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException


def _pub_from_xonly(xonly_hex: str) -> PublicKey:
    return PublicKey(bytes.fromhex("02" + xonly_hex))


def nip04_shared_x(priv_hex: str, xonly_pub_hex: str) -> bytes:
    """ECDH x-coordinate as a raw 32-byte AES-256 key (NIP-04 spec)."""
    priv = PrivateKey(bytes.fromhex(priv_hex))
    pub = _pub_from_xonly(xonly_pub_hex)
    shared_point = pub.multiply(priv.secret)
    return shared_point.format(compressed=True)[1:33]


def nip04_encrypt(plaintext: bytes, sender_priv_hex: str, recipient_xonly_pub_hex: str) -> str:
    """NIP-04 kind-4 ciphertext: `<b64_ct>?iv=<b64_iv>`.

    Symmetric key = ECDH x-coord (32 bytes). AES-256-CBC + PKCS7 padding.
    """
    key = nip04_shared_x(sender_priv_hex, recipient_xonly_pub_hex)
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = cipher.update(padded) + cipher.finalize()
    return f"{base64.b64encode(ct).decode('ascii')}?iv={base64.b64encode(iv).decode('ascii')}"


def nip04_decrypt(nip04_ct: str, recipient_priv_hex: str, sender_xonly_pub_hex: str) -> bytes:
    """Inverse of `nip04_encrypt`. Raises 422 on any structural or auth failure."""
    if "?iv=" not in nip04_ct:
        raise HTTPException(status_code=422, detail="Malformed NIP-04 ciphertext")
    ct_b64, iv_b64 = nip04_ct.split("?iv=", 1)
    try:
        ct = base64.b64decode(ct_b64)
        iv = base64.b64decode(iv_b64)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"NIP-04 base64: {exc}")
    key = nip04_shared_x(recipient_priv_hex, sender_xonly_pub_hex)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    try:
        padded = cipher.update(ct) + cipher.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"NIP-04 decrypt: {exc}") from exc


def envelope_parts(entry, default_sender_pubkey: str | None) -> tuple[str, str | None]:
    """Split a stored NIP-04 envelope into (ciphertext, sender_pubkey).

    Two shapes exist (T3.12 pt.2c):

    - legacy `"<ct>"` — the sender was always the message author, so the caller
      supplies it as `default_sender_pubkey`;
    - `{"ct": "<ct>", "sender_pubkey": "<hex>"}` — carries its own sender.

    The second shape exists because NIP-04 is ECDH: re-addressing an envelope to
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
        "sender":  "<NIP-04 ct string>",
        "carrier": "<NIP-04 ct string>",
        "arbiter": "<NIP-04 ct string>"
      },
      "read_packages": {
        "sender":  "<NIP-04 ct of session_key>",
        "carrier": "<NIP-04 ct of session_key>"
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
            if not isinstance(val, str) or "?iv=" not in val:
                raise HTTPException(
                    status_code=422,
                    detail=f"wrapped_shares.{role} must be a NIP-04 ct string",
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
