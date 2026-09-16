"""T3.12.09 — the arbiter pool: who is offered a dispute, and when it moves on.

`IMPLEMENTATIONPLAN §3.12.6`. Owner's answers 2026-09-14: the pool is the
default mode. The platform offers a dispute to one arbiter, picked at random
among the least loaded, who accepts or declines; a refusal or
`arbiter_handoff_hours` of silence pass it to the next, and nobody who passed is
asked about it again. The other mode, `requests`, leaves open disputes for
arbiters to take themselves (`api.admin.claim_dispute`).

**A party is excluded in the query, not refused afterwards** (п. 3): the
sender, the carrier and the recipient never enter the candidate list, so no
arbiter is offered a dispute about their own deal. `api.admin.accept_dispute`
checks again, because a role can be granted to a party after the offer.

`pool` narrows the candidates for tests: `vimana_test` is never reset and holds
every arbiter any test ever made.

Functions (PROJECT §6.2a):
- `mode(db)` — `pool` or `requests`.
  Called by: `offer_next`, `api.admin.list_disputes`, `api.admin.claim_dispute`,
  `tasks.cleanup._reassign_arbiters`.
- `choose_arbiter(db, dispute, deal, *, pool=None)` — one arbiter id, or None.
  Called by: `offer_next`.
- `offer_next(db, dispute, *, pool=None)` — withdraw the standing offer, if
  any, and make the next one. Does not commit. Called by:
  `api.admin.open_dispute`, `api.admin.decline_dispute`,
  `tasks.cleanup._check_delivery_timers`, `tasks.cleanup._reassign_arbiters`.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.params import resolve
from app.models.deal import Deal, Dispute, DisputeStatus
from app.models.user import User

logger = logging.getLogger(__name__)

POOL = "pool"
REQUESTS = "requests"


async def offer_label(db: AsyncSession, dispute: Dispute) -> str:
    """The deal's number, for the letter. Empty when the deal or its cargo is
    gone — a letter with no number is still better than no letter."""
    from app.core.cargo import deal_no
    from app.models.marketplace import Cargo

    deal = await db.get(Deal, dispute.deal_id)
    if deal is None:
        return ""
    cargo = await db.get(Cargo, deal.cargo_id)
    return deal_no(cargo.shipment_no if cargo else None, deal.position) or ""


def announce_offer(arbiter_id: uuid.UUID | None, label: str) -> None:
    """Tell the arbiter they were picked. **Call after the commit.**

    Queued before it, the letter would announce a dispute a rollback took back.
    A failure to queue is logged and nothing else: the offer stands either way,
    and the hourly sweep passes it on if the arbiter never answers.

    Called by: `api.admin.open_dispute`, `api.admin.decline_dispute`,
    `tasks.cleanup._check_delivery_timers`, `tasks.cleanup._reassign_arbiters`.
    """
    if arbiter_id is None:
        return
    try:
        from app.tasks.notifications import send_dispute_offered

        send_dispute_offered.delay(str(arbiter_id), label)
    except Exception:  # noqa: BLE001 — a letter never blocks an assignment
        logger.warning("dispute offer letter not queued for %s", arbiter_id)


async def mode(db: AsyncSession) -> str:
    # Anything but `requests` reads as the pool: a mistyped value must not
    # leave disputes with nobody to take them.
    value = str(await resolve(db, "arbiter_assignment_mode"))
    return REQUESTS if value == REQUESTS else POOL


async def _loads(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Disputes in work per arbiter: claimed ones plus offers still standing."""
    load = dict.fromkeys(ids, 0)
    claimed = await db.execute(
        select(Dispute.arbiter_id, func.count())
        .where(Dispute.arbiter_id.in_(ids), Dispute.status == DisputeStatus.claimed)
        .group_by(Dispute.arbiter_id)
    )
    offered = await db.execute(
        select(Dispute.offered_to_id, func.count())
        .where(Dispute.offered_to_id.in_(ids))
        .group_by(Dispute.offered_to_id)
    )
    for who, count in [*claimed.all(), *offered.all()]:
        load[who] += count
    return load


async def choose_arbiter(
    db: AsyncSession,
    dispute: Dispute,
    deal: Deal,
    *,
    pool: list[uuid.UUID] | None = None,
) -> uuid.UUID | None:
    excluded = {p for p in (deal.sender_id, deal.carrier_id, deal.recipient_id) if p}
    excluded.update(uuid.UUID(p) for p in (dispute.passed_over or []))

    query = select(User.id).where(User.roles.contains(["arbiter"]))
    if excluded:
        query = query.where(User.id.not_in(excluded))
    if pool is not None:
        query = query.where(User.id.in_(pool))
    candidates = list((await db.execute(query)).scalars())
    if not candidates:
        return None

    cap = int(await resolve(db, "arbiter_max_open_disputes"))
    load = await _loads(db, candidates)
    free = [c for c in candidates if load[c] < cap]
    if not free:
        return None
    least = min(load[c] for c in free)
    return secrets.choice([c for c in free if load[c] == least])


async def offer_next(
    db: AsyncSession, dispute: Dispute, *, pool: list[uuid.UUID] | None = None
) -> uuid.UUID | None:
    if dispute.offered_to_id is not None:
        dispute.passed_over = [*(dispute.passed_over or []), str(dispute.offered_to_id)]
    dispute.offered_to_id = None
    dispute.offered_at = None
    if dispute.status is not DisputeStatus.open or await mode(db) != POOL:
        return None

    deal = await db.get(Deal, dispute.deal_id)
    chosen = await choose_arbiter(db, dispute, deal, pool=pool) if deal else None
    if chosen is not None:
        dispute.offered_to_id = chosen
        dispute.offered_at = datetime.now(timezone.utc)
    # Nobody free: the dispute stays open with no offer, and the hourly sweep
    # (`tasks.cleanup.reassign_arbiters`) tries again.
    return chosen
