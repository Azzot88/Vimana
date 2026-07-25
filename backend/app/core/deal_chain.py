"""T3.6 — Tamper-evident hash chain over `deal_events`.

## Why this exists

`DealEvent` already carries `nostr_sig`/`nostr_event_id` (T2.2 pt.2). A signature
proves **authorship of one record**. It does not prove:

- **completeness** — the server could silently never write an inconvenient event;
- **ordering** — rows can be reordered;
- **non-deletion** — a removed row leaves no trace.

Those three are exactly what an arbiter needs, because the DealVault is the
evidence layer the whole dispute rests on. The chain closes them: every entry
hashes the previous entry's hash, so removing, reordering, or editing any entry
invalidates every hash after it.

## Threat model — read this before trusting the chain

The chain defends against anyone who can write to the DB but cannot re-run this
module: a compromised backup, an SQL injection, a rogue DBA, a restore from a
doctored dump.

**It does not defend against the platform itself.** We assign `seq`, so we could
recompute an entire chain forward from any point. And Vimana is simultaneously
the arbiter (`ARBITER_USER_ID`, server-held nsec) and the record keeper — which
is precisely the configuration where "our log verifies fine, we checked" is not
an argument the losing party has to accept.

That gap is closed *outside* this module: `app.core.chain_anchor` periodically
publishes the chain head to third-party Nostr relays, signed by the platform
key. Once a head is anchored elsewhere with someone else's timestamp on it, the
history behind it can no longer be rewritten after the fact. **The chain without
the anchor is hygiene; chain + anchor is evidence.**

## Hash preimage

Field order is **fixed** — changing it invalidates every chain in the database.
If it ever must change, that is a new column and a versioned migration, not an
edit here.

    sha256(
        deal_id (16 bytes)          # scope binding — leads, so an entry cannot
                                    # be lifted from deal A and re-verified in B
        seq (8 bytes, big-endian)
        timestamp (RFC3339, UTC)
        event_type (ascii)
        presence byte + actor_id (16 bytes)
        presence byte + nostr_event_id (ascii)
        canonical_json(payload)
        prev_hash (32 bytes, GENESIS for the first entry)
    )

Two details that are easy to get wrong and expensive to discover later:

- **Presence bytes.** Every optional field is preceded by `\\x01` (present) or
  `\\x00` (absent). Without it `actor_id=None` and a crafted zero-UUID actor
  hash identically.
- **Canonical JSON is a hard error on failure.** A payload that will not
  serialize raises; it is never hashed as `{}`. A hash must never silently stand
  in an empty value for a real one.

`nostr_event_id` is inside the preimage on purpose: it binds the per-record
Nostr signature into the chain, so the two integrity mechanisms cannot be peeled
apart (swapping a signature invalidates the chain from that entry onward).

## Concurrency

`seq` must be gapless and monotonic per deal, so `append_deal_event` takes a
transaction-scoped Postgres advisory lock keyed on the deal before reading the
head. `pg_advisory_xact_lock` releases on commit *and* on rollback, including
when the request raises — no explicit unlock path to get wrong.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.signing import sign_deal_event
from app.models.deal import Attachment, Deal, DealEvent, DealEventType, DealVaultMessage
from app.models.user import User

#: Hashed in place of `prev_hash` for a deal's first entry. Stored as NULL.
GENESIS_HASH = b"\x00" * 32

HASH_SIZE = 32

_PRESENT = b"\x01"
_ABSENT = b"\x00"

#: T3.7 — event types accepted on a sealed deal. The seal freezes *content*
#: (messages, files, status transitions), not the audit trail:
#: - `dispute_opened` — a dispute may open after closing (problems surface
#:   post-confirm); it unseals the vault at the API layer. The chain records
#:   both the seal and the unseal, so nothing is hidden by the exception.
#: - `arbiter_opened` — arbiter access must stay on the record even for a
#:   sealed vault; refusing it would mean either losing the audit trail or
#:   blocking reads. Audit entries extend the chain past the `sealed` marker
#:   but change no content — verification treats the seal event's seq as the
#:   content boundary.
_ALLOWED_WHEN_SEALED = frozenset(
    {DealEventType.dispute_opened, DealEventType.arbiter_opened}
)


class ChainError(RuntimeError):
    """Raised when the chain cannot be extended or a payload cannot be hashed."""


class SealedError(ChainError):
    """Raised on append to a sealed deal. API layers map this to 409."""


def content_hash_of(ciphertext: bytes | None, nonce: bytes | None) -> str:
    """T3.7 — sha256 over a vault message's stored bytes (ciphertext || nonce).

    Hashing the *stored* bytes keeps verification decryption-free: for e2e
    messages the server never sees plaintext yet can still prove the blob is
    the one that was chained. Consequence (D-DVLT-PROTOCOL): rotating
    `MESSAGE_ENCRYPTION_KEY` must be envelope-style (re-wrap the key), never a
    re-encryption of the data — that would invalidate every content hash.
    """
    h = hashlib.sha256()
    h.update(bytes(ciphertext) if ciphertext is not None else b"")
    h.update(bytes(nonce) if nonce is not None else b"")
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, stable across machines.

    Raises `ChainError` rather than substituting a placeholder — see module doc.
    """
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ChainError(f"payload is not canonically serializable: {exc}") from exc


def _event_type_value(event_type: DealEventType | str) -> str:
    return event_type.value if hasattr(event_type, "value") else str(event_type)


def _rfc3339(ts: datetime) -> str:
    """UTC-normalised RFC3339. Postgres timestamptz round-trips at microsecond
    resolution, so the recomputed string matches the one hashed at write time."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


def compute_entry_hash(
    *,
    deal_id: uuid.UUID,
    seq: int,
    timestamp: datetime,
    event_type: DealEventType | str,
    actor_id: uuid.UUID | None,
    nostr_event_id: str | None,
    payload: dict | None,
    prev_hash: bytes | None,
) -> bytes:
    """SHA-256 over the entry's scope, position, content, and chain link."""
    h = hashlib.sha256()
    h.update(deal_id.bytes)
    h.update(seq.to_bytes(8, "big"))
    h.update(_rfc3339(timestamp).encode("utf-8"))
    h.update(_event_type_value(event_type).encode("ascii"))
    if actor_id is None:
        h.update(_ABSENT)
    else:
        h.update(_PRESENT)
        h.update(actor_id.bytes)
    if nostr_event_id is None:
        h.update(_ABSENT)
    else:
        h.update(_PRESENT)
        h.update(nostr_event_id.encode("ascii"))
    h.update(canonical_json(payload).encode("utf-8"))
    h.update(bytes(prev_hash) if prev_hash is not None else GENESIS_HASH)
    return h.digest()


def hash_of(evt: DealEvent) -> bytes:
    """Recompute an existing row's hash from its stored fields."""
    return compute_entry_hash(
        deal_id=evt.deal_id,
        seq=evt.seq,
        timestamp=evt.timestamp,
        event_type=evt.event_type,
        actor_id=evt.actor_id,
        nostr_event_id=evt.nostr_event_id,
        payload=evt.payload,
        prev_hash=evt.prev_hash,
    )


async def _lock_deal(db: AsyncSession, deal_id: uuid.UUID) -> None:
    """Serialise `seq` assignment for one deal. Released at commit/rollback."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"deal_chain:{deal_id}"},
    )


async def head_of(db: AsyncSession, deal_id: uuid.UUID) -> tuple[int, bytes] | None:
    """`(seq, entry_hash)` of the deal's latest entry, or None for an empty chain."""
    row = (
        await db.execute(
            select(DealEvent.seq, DealEvent.entry_hash)
            .where(DealEvent.deal_id == deal_id)
            .order_by(DealEvent.seq.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return int(row[0]), bytes(row[1])


async def append_deal_event(
    db: AsyncSession,
    *,
    deal_id: uuid.UUID,
    event_type: DealEventType,
    actor_id: uuid.UUID | None,
    payload: dict | None = None,
    author: User | None = None,
) -> DealEvent:
    """Append one entry to a deal's chain. **The only supported way to write a
    `DealEvent`** — `seq`/`entry_hash` are NOT NULL in the schema, so a bare
    `DealEvent(...)` + `db.add()` fails loudly at flush instead of silently
    creating an unchained row.

    `author` drives Nostr signing (unchanged T2.2 pt.2 semantics: custodial →
    server signs, self-custody → left unsigned, None → unsigned). Signing runs
    *before* hashing so `nostr_event_id` is bound into the chain.

    Flushes before returning so a second call in the same transaction sees this
    entry as the head.
    """
    await _lock_deal(db, deal_id)

    # T3.7 — a sealed vault accepts no new entries except a dispute opening
    # (which unseals it at the API layer). Checked under the advisory lock so
    # a concurrent seal cannot race past it.
    if event_type not in _ALLOWED_WHEN_SEALED:
        sealed_at = (
            await db.execute(select(Deal.sealed_at).where(Deal.id == deal_id))
        ).scalar_one_or_none()
        if sealed_at is not None:
            raise SealedError(f"deal {deal_id} is sealed — append refused")

    head = await head_of(db, deal_id)
    seq = 1 if head is None else head[0] + 1
    prev_hash = None if head is None else head[1]

    evt = DealEvent(
        deal_id=deal_id,
        event_type=event_type,
        actor_id=actor_id,
        payload=payload,
        # Set explicitly rather than leaning on server_default: the value has to
        # be known in Python to go into the hash.
        timestamp=datetime.now(timezone.utc),
        seq=seq,
        prev_hash=prev_hash,
    )
    sign_deal_event(evt, author)
    evt.entry_hash = compute_entry_hash(
        deal_id=deal_id,
        seq=seq,
        timestamp=evt.timestamp,
        event_type=event_type,
        actor_id=actor_id,
        nostr_event_id=evt.nostr_event_id,
        payload=payload,
        prev_hash=prev_hash,
    )
    db.add(evt)
    await db.flush()
    return evt


async def verify_chain(db: AsyncSession, deal_id: uuid.UUID) -> dict:
    """Walk a deal's chain and recompute every hash.

    Returns `{ok, length, head_seq, head_hash, broken_at, reason}`. `broken_at`
    is the `seq` of the first entry that fails, which is where tampering
    happened — every entry after it fails as a consequence, so only the first
    one is reported.

    An empty chain is `ok` (a deal with no events yet is not a broken deal).
    """
    # A caller may have updated rows via raw SQL after loading them through
    # the ORM (that is exactly what tamper-detection tests do). With
    # `expire_on_commit=False` the identity map still holds the pre-tamper
    # values — dropping them forces a fresh SELECT so we hash what is
    # actually in the DB, not what we happened to see last.
    db.expire_all()

    events = (
        (
            await db.execute(
                select(DealEvent)
                .where(DealEvent.deal_id == deal_id)
                .order_by(DealEvent.seq.asc())
            )
        )
        .scalars()
        .all()
    )

    if not events:
        return {
            "ok": True,
            "length": 0,
            "head_seq": None,
            "head_hash": None,
            "broken_at": None,
            "reason": None,
        }

    expected_prev: bytes | None = None
    for index, evt in enumerate(events, start=1):
        if evt.seq != index:
            return _broken(events, evt.seq, f"expected seq {index}, found {evt.seq}")

        stored_prev = bytes(evt.prev_hash) if evt.prev_hash is not None else None
        if stored_prev != expected_prev:
            return _broken(events, evt.seq, "prev_hash does not match preceding entry")

        try:
            recomputed = hash_of(evt)
        except ChainError as exc:
            return _broken(events, evt.seq, str(exc))
        if recomputed != bytes(evt.entry_hash):
            return _broken(events, evt.seq, "entry content does not match stored hash")

        expected_prev = bytes(evt.entry_hash)

    head = events[-1]
    return {
        "ok": True,
        "length": len(events),
        "head_seq": head.seq,
        "head_hash": bytes(head.entry_hash).hex(),
        "broken_at": None,
        "reason": None,
    }


def _broken(events: list[DealEvent], seq: int, reason: str) -> dict:
    return {
        "ok": False,
        "length": len(events),
        "head_seq": events[-1].seq,
        "head_hash": bytes(events[-1].entry_hash).hex(),
        "broken_at": seq,
        "reason": reason,
    }


async def verify_content(db: AsyncSession, deal_id: uuid.UUID) -> dict:
    """T3.7 — check chained content pointers against the stored content.

    `verify_chain` proves the *log* is intact; this proves the log still points
    at the *content* it was written for: every `message_added` entry's
    `content_hash` must match the stored ciphertext bytes, every `file_added`
    entry's `file_hash` must match the attachment row. A deleted message or a
    swapped ciphertext shows up here even though the chain itself verifies.

    Returns `{content_ok, mismatches, checked_messages, checked_files}` where
    each mismatch is `{seq, kind, ref_id, reason}`. R2 object integrity is out
    of scope — clients compare a download against `file_hash` themselves.
    """
    db.expire_all()

    events = (
        (
            await db.execute(
                select(DealEvent)
                .where(
                    DealEvent.deal_id == deal_id,
                    DealEvent.event_type.in_(
                        [
                            DealEventType.message_added,
                            DealEventType.file_added,
                            DealEventType.identity_ref,
                        ]
                    ),
                )
                .order_by(DealEvent.seq.asc())
            )
        )
        .scalars()
        .all()
    )

    mismatches: list[dict] = []
    checked_messages = 0
    checked_files = 0
    checked_identity = 0

    for evt in events:
        payload = evt.payload or {}
        if evt.event_type == DealEventType.identity_ref:
            # T3.9 — triple match: chain payload == deal attachment copy ==
            # canonical IdentityContainer. Any divergence between the two
            # vaults (or a deleted row) surfaces here.
            from app.models.verification import IdentityContainer

            checked_identity += 1
            ref_hash = payload.get("doc_hash")
            att_ref = payload.get("attachment_id")
            att = await db.get(Attachment, uuid.UUID(att_ref)) if att_ref else None
            if att is None:
                mismatches.append(
                    {"seq": evt.seq, "kind": "identity", "ref_id": att_ref, "reason": "identity attachment missing"}
                )
            elif att.file_hash != ref_hash:
                mismatches.append(
                    {"seq": evt.seq, "kind": "identity", "ref_id": att_ref, "reason": "identity copy hash mismatch"}
                )
            cont_ref = payload.get("container_id")
            cont = (
                await db.get(IdentityContainer, uuid.UUID(cont_ref)) if cont_ref else None
            )
            if cont is None:
                mismatches.append(
                    {"seq": evt.seq, "kind": "identity", "ref_id": cont_ref, "reason": "identity container missing"}
                )
            elif cont.doc_hash != ref_hash:
                mismatches.append(
                    {"seq": evt.seq, "kind": "identity", "ref_id": cont_ref, "reason": "identity container hash mismatch"}
                )
            continue
        if evt.event_type == DealEventType.message_added:
            checked_messages += 1
            ref = payload.get("message_id")
            msg = await db.get(DealVaultMessage, uuid.UUID(ref)) if ref else None
            if msg is None or msg.deal_id != deal_id:
                mismatches.append(
                    {"seq": evt.seq, "kind": "message", "ref_id": ref, "reason": "message missing"}
                )
                continue
            recomputed = content_hash_of(msg.text_ciphertext, msg.text_nonce)
            if recomputed != payload.get("content_hash"):
                mismatches.append(
                    {"seq": evt.seq, "kind": "message", "ref_id": ref, "reason": "content hash mismatch"}
                )
        else:
            checked_files += 1
            ref = payload.get("attachment_id")
            att = await db.get(Attachment, uuid.UUID(ref)) if ref else None
            if att is None:
                mismatches.append(
                    {"seq": evt.seq, "kind": "file", "ref_id": ref, "reason": "attachment missing"}
                )
                continue
            if att.file_hash != payload.get("file_hash"):
                mismatches.append(
                    {"seq": evt.seq, "kind": "file", "ref_id": ref, "reason": "file hash mismatch"}
                )

    return {
        "content_ok": not mismatches,
        "mismatches": mismatches,
        "checked_messages": checked_messages,
        "checked_files": checked_files,
        "checked_identity": checked_identity,
    }
