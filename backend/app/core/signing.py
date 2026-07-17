"""T2.2 pt.2 — NIP-01 Nostr event signing for DealVault records.

Vault messages and deal events get signed as Nostr events (NIP-01):

    id = sha256([0, pubkey, created_at, kind, tags, content])
    sig = schnorr_sign(id, nsec)

Kinds are application-scoped (NIP-01 §Basic event kinds — regular range):
- 4801 = deal vault message
- 4802 = deal state event

**Vault message** (kind 4801): client-authored user content. Content = plaintext
(server encrypts at rest afterwards). Tags = `[["k","vault_message"],["deal",<uuid>]]`
(no message-id d-tag — client cannot know the server-assigned id yet). Self-custody
users MUST sign client-side via NIP-07; custodial users → server signs.

**Deal event** (kind 4802): server-produced state transitions. Content = canonical
JSON of `{event_type, actor_id, payload}`. Tags = `[["k","deal_event"],["deal",<uuid>],
["e", event_type]]`. Self-custody users skip signing (no NIP-07 round-trip for
button clicks) — `nostr_sig` stays NULL; audit still relies on `actor_id`.

Old-format sigs from T2.2 pt.1 remain in DB unchanged; their `nostr_event_id`
column stays NULL — that is the on-disk marker distinguishing formats.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.core.keypair import (
    decrypt_nsec,
    sign_event_id,
    verify_event_id,
)
from app.models.deal import DealEvent, DealVaultMessage
from app.models.user import User

NOSTR_KIND_VAULT_MESSAGE = 4801
NOSTR_KIND_DEAL_EVENT = 4802

# NIP-01 §7 recommends rejecting events with created_at drifting > 15 min;
# we use a tighter 5-min window since our clients are online-only.
CLOCK_SKEW_SEC = 5 * 60


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _b64(v: bytes | None) -> str | None:
    if v is None:
        return None
    return base64.b64encode(bytes(v)).decode("ascii")


def _now_unix() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def _tags_vault_message(msg: DealVaultMessage) -> list[list[str]]:
    tags: list[list[str]] = [
        ["k", "vault_message"],
        ["deal", str(msg.deal_id)],
    ]
    if msg.is_system:
        tags.append(["system", "1"])
    return tags


def _content_vault_message(msg: DealVaultMessage) -> str:
    """Content = plaintext (bound to sig BEFORE at-rest encryption).

    Client can produce this without knowing server-side encryption; server can
    reproduce it after decrypting via the `text` property.
    """
    return msg.text or ""


def _tags_deal_event(evt: DealEvent) -> list[list[str]]:
    et = (
        evt.event_type.value
        if hasattr(evt.event_type, "value")
        else str(evt.event_type)
    )
    return [
        ["k", "deal_event"],
        ["deal", str(evt.deal_id)],
        ["e", et],
    ]


def _content_deal_event(evt: DealEvent) -> str:
    et = (
        evt.event_type.value
        if hasattr(evt.event_type, "value")
        else str(evt.event_type)
    )
    return _canonical_json(
        {
            "event_type": et,
            "actor_id": str(evt.actor_id) if evt.actor_id else None,
            "payload": evt.payload,
        }
    )


def compute_event_id(
    pubkey_hex: str,
    created_at: int,
    kind: int,
    tags: list[list[str]],
    content: str,
) -> str:
    """NIP-01 event id = sha256(canonical JSON of [0, pubkey, ts, kind, tags, content])."""
    serialized = json.dumps(
        [0, pubkey_hex, created_at, kind, tags, content],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _server_sign(
    record,
    kind: int,
    tags: list[list[str]],
    content: str,
    author: User,
) -> None:
    ts = _now_unix()
    event_id = compute_event_id(author.nostr_pubkey, ts, kind, tags, content)
    nsec_hex = decrypt_nsec(bytes(author.nsec_nonce), bytes(author.nsec_encrypted))
    record.nostr_sig = sign_event_id(event_id, nsec_hex)
    record.nostr_event_id = event_id
    record.nostr_created_at = ts
    record.nostr_pubkey = author.nostr_pubkey


def _apply_pre_signed(
    record,
    kind: int,
    tags: list[list[str]],
    content: str,
    author: User,
    sig: str,
    ts: int,
) -> None:
    if not author.nostr_pubkey:
        raise HTTPException(status_code=422, detail="Author has no npub for verification")
    now = _now_unix()
    if abs(ts - now) > CLOCK_SKEW_SEC:
        raise HTTPException(
            status_code=422,
            detail="nostr_created_at outside acceptable clock skew (±5 min)",
        )
    event_id = compute_event_id(author.nostr_pubkey, ts, kind, tags, content)
    if not verify_event_id(event_id, sig, author.nostr_pubkey):
        raise HTTPException(status_code=422, detail="Invalid nostr_sig")
    record.nostr_sig = sig
    record.nostr_event_id = event_id
    record.nostr_created_at = ts
    record.nostr_pubkey = author.nostr_pubkey


def sign_vault_message(
    msg: DealVaultMessage,
    author: User | None,
    pre_signed_sig: str | None = None,
    pre_signed_ts: int | None = None,
) -> None:
    """Sign a vault message. Strict for self-custody (requires pre-signed).

    - System records (author=None) → leave unsigned.
    - `pre_signed_sig` given → verify + attach (needs `pre_signed_ts`).
    - Self-custody without pre_signed → 422.
    - Custodial → server signs.
    """
    if author is None:
        return
    tags = _tags_vault_message(msg)
    content = _content_vault_message(msg)
    if pre_signed_sig is not None:
        if pre_signed_ts is None:
            raise HTTPException(
                status_code=422,
                detail="nostr_created_at required alongside nostr_sig",
            )
        _apply_pre_signed(
            msg, NOSTR_KIND_VAULT_MESSAGE, tags, content, author, pre_signed_sig, pre_signed_ts
        )
        return
    if author.key_self_custody:
        raise HTTPException(
            status_code=422,
            detail="Self-custody account requires client-signed nostr_sig",
        )
    if (
        author.nsec_encrypted is None
        or author.nsec_nonce is None
        or not author.nostr_pubkey
    ):
        return  # no keypair — leave unsigned (backward-compat during migration)
    _server_sign(msg, NOSTR_KIND_VAULT_MESSAGE, tags, content, author)


def sign_deal_event(evt: DealEvent, author: User | None) -> None:
    """Sign a deal-state event. Lenient for self-custody (leaves unsigned).

    Rationale: deal events are triggered by button clicks (accept/confirm/etc.);
    requiring a NIP-07 round-trip on every click harms UX. Actor attribution
    stays via `actor_id`; Nostr sig is a bonus for custodial users.
    """
    if author is None:
        return
    if author.key_self_custody:
        return  # skip signing for self-custody
    if (
        author.nsec_encrypted is None
        or author.nsec_nonce is None
        or not author.nostr_pubkey
    ):
        return
    _server_sign(
        evt,
        NOSTR_KIND_DEAL_EVENT,
        _tags_deal_event(evt),
        _content_deal_event(evt),
        author,
    )


def build_vault_message_event_skeleton(
    deal_id: str,
    text: str,
    is_system: bool,
    pubkey_hex: str,
    created_at: int,
) -> dict:
    """Frontend/NIP-07 mirror — returns the exact event object shape a client
    should pass to `window.nostr.signEvent()`. Kept here so backend and frontend
    stay in sync: whenever the shape changes, both sides regenerate from this."""

    class _Stub:
        pass

    stub = _Stub()
    stub.deal_id = deal_id  # type: ignore[attr-defined]
    stub.is_system = is_system  # type: ignore[attr-defined]
    stub.text = text  # type: ignore[attr-defined]
    stub.text_ciphertext = None  # type: ignore[attr-defined]
    stub.text_nonce = None  # type: ignore[attr-defined]
    tags = _tags_vault_message(stub)  # type: ignore[arg-type]
    content = text or ""
    return {
        "kind": NOSTR_KIND_VAULT_MESSAGE,
        "pubkey": pubkey_hex,
        "created_at": created_at,
        "tags": tags,
        "content": content,
    }
