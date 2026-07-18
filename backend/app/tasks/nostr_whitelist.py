"""T3.5 pt.2 — refresh strfry writePolicy whitelist file.

WoT-gate source of truth = the same trust graph T2.4 built. Any user with a
`nostr_pubkey` AND at least one incoming trust edge (peer_verified, dealt_with,
or invited — see T2.4 weights) gets write permission on our relay. Isolated
new accounts stay read-only until someone vouches for them.

Output: newline-separated hex pubkeys in `NOSTR_ALLOWED_PUBKEYS_FILE`
(default `/data/allowed_pubkeys.txt` — mounted into strfry container).
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select

from app.core.database import SyncSessionLocal
from app.models.trust import TrustEdge
from app.models.user import User
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.nostr_whitelist.refresh_allowed_pubkeys")
def refresh_allowed_pubkeys() -> dict:
    path = os.getenv("NOSTR_ALLOWED_PUBKEYS_FILE", "/data/allowed_pubkeys.txt")
    with SyncSessionLocal() as db:
        # All npubs that appear as `to_user_id` in at least one active trust edge
        # OR that carry a peer_verified badge — plus superusers as safety net.
        rows = db.execute(
            select(User.nostr_pubkey).where(
                User.nostr_pubkey.isnot(None),
                User.id.in_(
                    select(TrustEdge.to_user_id).where(TrustEdge.revoked_at.is_(None))
                ),
            )
        ).all()
        pubkeys = {r[0] for r in rows if r[0]}

        # Include superusers/arbiters explicitly.
        extra_rows = db.execute(
            select(User.nostr_pubkey).where(
                User.nostr_pubkey.isnot(None),
                User.role.in_(("arbiter", "superuser")),
            )
        ).all()
        pubkeys.update(r[0] for r in extra_rows if r[0])

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    try:
        with open(path, "w") as f:
            for pk in sorted(pubkeys):
                f.write(pk + "\n")
    except OSError as exc:
        logger.warning("could not write allowed_pubkeys file at %s: %s", path, exc)
        return {"error": str(exc), "count": len(pubkeys)}

    return {"path": path, "count": len(pubkeys)}
