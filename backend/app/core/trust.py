"""T2.4 — Trust Graph helpers.

Insertion is idempotent through the unique constraint
`(from_user_id, to_user_id, kind, source_ref)`: on collision we skip. This
lets callers safely re-run without checking existence first.

Sybil guard: `peer_verified` edges REQUIRE at least one closed Deal between
the pair. Anything else raises `SybilGuardError`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealStatus
from app.models.trust import TrustEdge, TrustEdgeKind
from app.models.user import User


class SybilGuardError(RuntimeError):
    """peer_verified edge attempted without a closed Deal between the pair."""


_WEIGHTS = {
    TrustEdgeKind.peer_verified: 1.0,
    TrustEdgeKind.dealt_with: 0.5,
    TrustEdgeKind.invited: 0.2,
}


async def _pair_has_closed_deal(
    db: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> bool:
    q = select(func.count(Deal.id)).where(
        or_(
            and_(Deal.sender_id == a, Deal.carrier_id == b),
            and_(Deal.sender_id == b, Deal.carrier_id == a),
        ),
        Deal.status.in_([DealStatus.closed, DealStatus.confirmed]),
    )
    return (await db.scalar(q) or 0) > 0


async def add_edge(
    db: AsyncSession,
    *,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    kind: TrustEdgeKind,
    source_ref: str | None = None,
    check_sybil: bool = True,
) -> None:
    """Idempotent edge insert. Symmetric pairs (dealt_with, invited) should
    be inserted twice by the caller — this helper stays one-directional so
    callers keep control of semantics."""
    if from_user_id == to_user_id:
        return
    if kind == TrustEdgeKind.peer_verified and check_sybil:
        if not await _pair_has_closed_deal(db, from_user_id, to_user_id):
            raise SybilGuardError(
                "peer_verified edge requires at least one closed Deal between the pair"
            )
    stmt = pg_insert(TrustEdge).values(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        kind=kind,
        weight=_WEIGHTS[kind],
        source_ref=source_ref,
    )
    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_trust_edge_pair_kind_source"
    )
    await db.execute(stmt)


async def add_dealt_with(db: AsyncSession, deal: Deal) -> None:
    """Symmetric dealt_with pair on deal close."""
    src = f"deal:{deal.id}"
    await add_edge(
        db,
        from_user_id=deal.sender_id,
        to_user_id=deal.carrier_id,
        kind=TrustEdgeKind.dealt_with,
        source_ref=src,
        check_sybil=False,
    )
    await add_edge(
        db,
        from_user_id=deal.carrier_id,
        to_user_id=deal.sender_id,
        kind=TrustEdgeKind.dealt_with,
        source_ref=src,
        check_sybil=False,
    )


async def add_invited(
    db: AsyncSession,
    *,
    inviter_id: uuid.UUID,
    invitee_id: uuid.UUID,
    invite_token: str,
) -> None:
    """Symmetric invited pair on invite acceptance."""
    src = f"invite:{invite_token}"
    await add_edge(
        db,
        from_user_id=inviter_id,
        to_user_id=invitee_id,
        kind=TrustEdgeKind.invited,
        source_ref=src,
        check_sybil=False,
    )
    await add_edge(
        db,
        from_user_id=invitee_id,
        to_user_id=inviter_id,
        kind=TrustEdgeKind.invited,
        source_ref=src,
        check_sybil=False,
    )


async def revoke_edge(db: AsyncSession, edge_id: uuid.UUID) -> None:
    edge = await db.get(TrustEdge, edge_id)
    if edge and edge.revoked_at is None:
        edge.revoked_at = datetime.now(timezone.utc)
        await db.flush()


# ─────────────────────────────────────────────────────────────
# Denormalized counts
# ─────────────────────────────────────────────────────────────


async def refresh_trust_counts(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Recompute `verifications_issued_count`, `verifications_received_count`,
    `dealt_with_count` for one user."""
    issued = await db.scalar(
        select(func.count(TrustEdge.id)).where(
            TrustEdge.from_user_id == user_id,
            TrustEdge.kind == TrustEdgeKind.peer_verified,
            TrustEdge.revoked_at.is_(None),
        )
    )
    received = await db.scalar(
        select(func.count(TrustEdge.id)).where(
            TrustEdge.to_user_id == user_id,
            TrustEdge.kind == TrustEdgeKind.peer_verified,
            TrustEdge.revoked_at.is_(None),
        )
    )
    dealt = await db.scalar(
        select(func.count(TrustEdge.id)).where(
            TrustEdge.from_user_id == user_id,
            TrustEdge.kind == TrustEdgeKind.dealt_with,
            TrustEdge.revoked_at.is_(None),
        )
    )
    user = await db.get(User, user_id)
    if user is None:
        return
    user.verifications_issued_count = issued or 0
    user.verifications_received_count = received or 0
    user.dealt_with_count = dealt or 0
    await db.flush()


# ─────────────────────────────────────────────────────────────
# BFS
# ─────────────────────────────────────────────────────────────


async def bfs_circles(
    db: AsyncSession,
    *,
    root_id: uuid.UUID,
    depth: int = 3,
    kind: TrustEdgeKind | None = None,
) -> dict[int, list[uuid.UUID]]:
    """Return `{level: [user_ids]}` up to `depth`. Level 0 is the root itself.

    If `kind` is provided, only edges of that kind are traversed. Weights are
    ignored for now — we return raw circles. Revoked edges are excluded.
    """
    depth = max(1, min(depth, 6))
    visited: set[uuid.UUID] = {root_id}
    levels: dict[int, list[uuid.UUID]] = {0: [root_id]}
    frontier: list[uuid.UUID] = [root_id]

    # One query per level, not per node. The traversal is the same breadth-first
    # walk; what changed is that a level's neighbours are asked for in a single
    # `IN (...)` instead of a round trip per member. At depth 6 on a graph of any
    # size that is the difference between six queries and one per person reached
    # — which is why the follow-up recorded for this was a Redis cache. Caching
    # the answer would have hidden the shape of the question (T_PERF.1).
    for level in range(1, depth + 1):
        if not frontier:
            break
        conditions = [
            TrustEdge.from_user_id.in_(frontier),
            TrustEdge.revoked_at.is_(None),
        ]
        if kind is not None:
            conditions.append(TrustEdge.kind == kind)
        rows = (
            await db.execute(
                select(TrustEdge.to_user_id).where(*conditions).distinct()
            )
        ).scalars().all()
        next_frontier: list[uuid.UUID] = []
        for target in rows:
            if target in visited:
                continue
            visited.add(target)
            next_frontier.append(target)
        if next_frontier:
            levels[level] = next_frontier
        frontier = next_frontier

    return levels


async def distance_between(
    db: AsyncSession,
    *,
    root_id: uuid.UUID,
    target_id: uuid.UUID,
    max_depth: int = 6,
    kind: TrustEdgeKind | None = None,
) -> int | None:
    """Shortest-path hop count from root to target; None if unreachable."""
    if root_id == target_id:
        return 0
    levels = await bfs_circles(db, root_id=root_id, depth=max_depth, kind=kind)
    for level, users in levels.items():
        if target_id in users:
            return level
    return None
