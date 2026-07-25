"""T3.6 — External anchoring of deal chain heads to Nostr.

`app.core.deal_chain` makes tampering *detectable by us*. This module makes it
detectable by everyone else, which is the part that matters when we are the
arbiter in our own dispute.

## What anchoring buys

We assign `seq`, so we could in principle recompute a whole chain forward and
present a clean log. Publishing the head — `(deal_id, seq, entry_hash)` — to
relays we do not control, signed by the platform key, removes that option after
the fact: a rewritten history produces a different head, and the old head is
already sitting on someone else's disk with their timestamp on it.

The evidential weight comes from `NOSTR_FRIENDLY_RELAYS` (third parties), not
from `NOSTR_OWN_RELAY_URL` — we control our own strfry, so an anchor that only
landed there proves nothing. `publish_event` writes to both; we record the
per-relay result in `DealChainAnchor.relays` so an auditor can tell which of the
two actually happened.

## Cadence

Hourly, head-only: one event per deal that has grown since its last anchor, not
one per deal event. Anchoring the head covers every entry beneath it, because
each entry's hash includes its predecessor's — that is the whole point of the
chain. A deal with 50 events and no anchor produces one anchor event.

An anchor row is written only after at least one relay accepts. A failed publish
leaves no row, so the next tick simply retries the same head — no bookkeeping,
no partial state.

## Configuration

- `CHAIN_ANCHOR_NSEC` — 64-hex platform anchor key. Unset → anchoring is a no-op.
  Deliberately **not** a user key and not `ARBITER_USER_ID`'s key: the anchor is
  a statement by the platform about its own records, and mixing it into an
  identity that also signs deal events would blur who is attesting to what.
- `NOSTR_PUBLISH_ENABLED` — the same master switch as trip publishing. Anchoring
  cannot outrun the bridge it rides on.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deal_chain import canonical_json
from app.core.keypair import npub_from_nsec, sign_event_id
from app.core.nostr_publish import is_publish_enabled, publish_event
from app.core.signing import compute_event_id
from app.models.deal import DealChainAnchor, DealEvent

logger = logging.getLogger(__name__)

#: Application-scoped kind, continuing the 4801 (vault message) / 4802 (deal
#: event) series from T2.2 pt.2.
NOSTR_KIND_CHAIN_ANCHOR = 4803


def get_anchor_nsec() -> str | None:
    raw = os.getenv("CHAIN_ANCHOR_NSEC", "").strip()
    return raw or None


def is_anchoring_enabled() -> bool:
    return is_publish_enabled() and get_anchor_nsec() is not None


def build_anchor_event(
    *,
    deal_id: uuid.UUID,
    seq: int,
    entry_hash_hex: str,
    nsec_hex: str,
) -> dict[str, Any]:
    """Assemble the signed NIP-01 anchor event.

    The head hash is duplicated into a tag (`h`) so relays and clients can filter
    on it without parsing content — content stays the authoritative copy.
    """
    pubkey_hex = npub_from_nsec(nsec_hex)
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    tags = [
        ["k", "chain_anchor"],
        ["deal", str(deal_id)],
        ["seq", str(seq)],
        ["h", entry_hash_hex],
        ["t", "vimana"],
    ]
    content = canonical_json(
        {
            "deal_id": str(deal_id),
            "seq": seq,
            "entry_hash": entry_hash_hex,
            "alg": "sha256-chain-v1",
        }
    )
    event_id = compute_event_id(pubkey_hex, ts, NOSTR_KIND_CHAIN_ANCHOR, tags, content)
    return {
        "id": event_id,
        "pubkey": pubkey_hex,
        "created_at": ts,
        "kind": NOSTR_KIND_CHAIN_ANCHOR,
        "tags": tags,
        "content": content,
        "sig": sign_event_id(event_id, nsec_hex),
    }


def find_unanchored_heads(db: Session, limit: int = 100) -> list[tuple[uuid.UUID, int]]:
    """Deals whose chain head is ahead of their last anchored seq.

    Includes deals that have never been anchored (`anchored_seq IS NULL`).
    """
    heads = (
        select(DealEvent.deal_id, func.max(DealEvent.seq).label("head_seq"))
        .group_by(DealEvent.deal_id)
        .subquery()
    )
    anchored = (
        select(
            DealChainAnchor.deal_id,
            func.max(DealChainAnchor.seq).label("anchored_seq"),
        )
        .group_by(DealChainAnchor.deal_id)
        .subquery()
    )
    rows = db.execute(
        select(heads.c.deal_id, heads.c.head_seq)
        .select_from(
            heads.outerjoin(anchored, heads.c.deal_id == anchored.c.deal_id)
        )
        .where(
            or_(
                anchored.c.anchored_seq.is_(None),
                anchored.c.anchored_seq < heads.c.head_seq,
            )
        )
        .order_by(heads.c.deal_id)
        .limit(limit)
    ).all()
    return [(row[0], int(row[1])) for row in rows]


def anchor_deal_head(db: Session, deal_id: uuid.UUID, seq: int, nsec_hex: str) -> dict:
    """Publish one deal's head and record it. Returns a per-deal result dict."""
    row = db.execute(
        select(DealEvent.entry_hash).where(
            DealEvent.deal_id == deal_id, DealEvent.seq == seq
        )
    ).first()
    if row is None:
        # The head moved between the scan and now — next tick picks up the new one.
        return {"deal_id": str(deal_id), "skipped": "head not found"}

    entry_hash = bytes(row[0])
    event = build_anchor_event(
        deal_id=deal_id,
        seq=seq,
        entry_hash_hex=entry_hash.hex(),
        nsec_hex=nsec_hex,
    )
    relays = asyncio.run(publish_event(event))
    if not any(relays.values()):
        # No relay took it — write nothing so the same head is retried.
        logger.warning("chain anchor rejected by all relays: deal=%s seq=%s", deal_id, seq)
        return {"deal_id": str(deal_id), "seq": seq, "published": False, "relays": relays}

    db.add(
        DealChainAnchor(
            deal_id=deal_id,
            seq=seq,
            entry_hash=entry_hash,
            nostr_event_id=event["id"],
            nostr_pubkey=event["pubkey"],
            relays=relays,
        )
    )
    db.commit()
    return {
        "deal_id": str(deal_id),
        "seq": seq,
        "published": True,
        "event_id": event["id"],
        "relays": relays,
    }


def anchor_pending(db: Session, limit: int = 100) -> dict:
    """Anchor every chain head that has moved since its last anchor."""
    nsec_hex = get_anchor_nsec()
    if not is_publish_enabled():
        return {"skipped": "publish disabled"}
    if nsec_hex is None:
        return {"skipped": "CHAIN_ANCHOR_NSEC not set"}

    results = [
        anchor_deal_head(db, deal_id, seq, nsec_hex)
        for deal_id, seq in find_unanchored_heads(db, limit=limit)
    ]
    published = sum(1 for r in results if r.get("published"))
    return {"scanned": len(results), "published": published, "results": results}
