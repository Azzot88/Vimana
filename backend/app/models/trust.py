"""T2.4 — Trust Graph (Web-of-Trust).

Edges accumulate from three sources:
- `peer_verified` (weight 1.0) — from `VerificationBadge(level=peer)` (T2.1).
  Sybil-guarded: requires at least one closed Deal between the pair.
- `dealt_with` (weight 0.5) — auto-inserted when a Deal is `confirmed`/`closed`.
- `invited` (weight 0.2) — auto-inserted when a Connection is accepted.

Edges are **directed** — publishing them symmetrically is done at insert time
where symmetry makes semantic sense (dealt_with and invited are mutual).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrustEdgeKind(str, enum.Enum):
    peer_verified = "peer_verified"
    dealt_with = "dealt_with"
    invited = "invited"


class TrustEdge(Base):
    __tablename__ = "trust_edges"
    __table_args__ = (
        UniqueConstraint(
            "from_user_id",
            "to_user_id",
            "kind",
            "source_ref",
            name="uq_trust_edge_pair_kind_source",
        ),
        # Edges *pointing at* a user — "verifications received" in
        # `refresh_trust_counts`. The outgoing direction needs nothing: it leads
        # the unique constraint above, and a leftmost prefix is an index
        # (T_PERF.1, 0034).
        Index("ix_trust_edges_to_user_id", "to_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[TrustEdgeKind] = mapped_column(SAEnum(TrustEdgeKind))
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
