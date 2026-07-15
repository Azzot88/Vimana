"""T2.2 — Nostr Schnorr signing for DealVault-like records.

Every `DealVaultMessage` and `DealEvent` gets a Schnorr signature over its
canonical payload:
- **Custodial** user → server decrypts nsec, signs at insert time.
- **Self-custody** user → client MUST supply `nostr_sig` in the request body;
  server verifies it against the user's npub before persisting.
- System-authored records (`sender_id=None` / `actor_id=None`) skip signing.

The exact payload shape is stable per model type (see `_payload_*`). Changing
it is a **breaking** event — history stops being verifiable. Add a version tag
to the payload before ever tweaking (`{"v": 2, ...}`).
"""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any

from fastapi import HTTPException

from app.core.keypair import decrypt_nsec, sign_event, verify_event
from app.models.deal import DealEvent, DealVaultMessage
from app.models.user import User


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _b64(v: bytes | None) -> str | None:
    if v is None:
        return None
    return base64.b64encode(bytes(v)).decode("ascii")


def _payload_vault_message(msg: DealVaultMessage) -> str:
    return _canonical_json(
        {
            "v": 1,
            "kind": "vault_message",
            "deal_id": str(msg.deal_id),
            "sender_id": str(msg.sender_id) if msg.sender_id else None,
            "text_ciphertext": _b64(msg.text_ciphertext),
            "text_nonce": _b64(msg.text_nonce),
            "is_system": bool(msg.is_system),
        }
    )


def _payload_deal_event(evt: DealEvent) -> str:
    return _canonical_json(
        {
            "v": 1,
            "kind": "deal_event",
            "deal_id": str(evt.deal_id),
            "event_type": evt.event_type.value
            if hasattr(evt.event_type, "value")
            else str(evt.event_type),
            "actor_id": str(evt.actor_id) if evt.actor_id else None,
            "payload": evt.payload,
        }
    )


def _apply(record, payload: str, author: User | None, pre_signed: str | None) -> None:
    """Set `record.nostr_sig` according to author's custody mode.

    Rules:
      - Author is None (system record) → leave sig as None.
      - `pre_signed` provided → verify against author's npub; on failure raise 422.
      - Author is self-custody and no `pre_signed` → 422 (client must sign).
      - Author has custodial nsec → server signs.
      - Otherwise (edge: no key at all) → leave sig as None.
    """
    if author is None:
        return
    if pre_signed:
        if not author.nostr_pubkey or not verify_event(
            payload, pre_signed, author.nostr_pubkey
        ):
            raise HTTPException(status_code=422, detail="Invalid nostr_sig")
        record.nostr_sig = pre_signed
        return
    if author.key_self_custody:
        raise HTTPException(
            status_code=422,
            detail="Self-custody account requires client-signed nostr_sig",
        )
    if author.nsec_encrypted is None or author.nsec_nonce is None:
        return  # no keypair — leave unsigned (backward-compat during migration)
    nsec_hex = decrypt_nsec(bytes(author.nsec_nonce), bytes(author.nsec_encrypted))
    record.nostr_sig = sign_event(payload, nsec_hex)


def sign_vault_message(
    msg: DealVaultMessage, author: User | None, pre_signed: str | None = None
) -> None:
    """Populate `msg.nostr_sig` in-place. Call before `db.add(msg)`."""
    _apply(msg, _payload_vault_message(msg), author, pre_signed)


def sign_deal_event(
    evt: DealEvent, author: User | None, pre_signed: str | None = None
) -> None:
    _apply(evt, _payload_deal_event(evt), author, pre_signed)


def get_signature_payload_vault_message(msg: DealVaultMessage) -> str:
    """Exposed for clients that need to compute the same payload locally (NIP-07 signing)."""
    return _payload_vault_message(msg)


def get_signature_payload_deal_event(evt: DealEvent) -> str:
    return _payload_deal_event(evt)
