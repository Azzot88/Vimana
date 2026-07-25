"""T3.6 — Celery task publishing deal chain heads to Nostr.

Sync session (`SyncSessionLocal`) like the other Celery tasks; the async publish
is bridged inside `app.core.chain_anchor`.
"""
from __future__ import annotations

import logging

from app.core.chain_anchor import anchor_pending, is_anchoring_enabled
from app.core.database import SyncSessionLocal
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.chain_anchor.anchor_deal_chains")
def anchor_deal_chains(limit: int = 100) -> dict:
    if not is_anchoring_enabled():
        return {"skipped": "anchoring disabled"}
    with SyncSessionLocal() as db:
        result = anchor_pending(db, limit=limit)
    logger.info(
        "chain anchor tick: scanned=%s published=%s",
        result.get("scanned"),
        result.get("published"),
    )
    return result
