"""T_UX.2 pt.4 — pin corridor RouteNote(s) as a DealVault system-message
when a Deal is created on a flagged corridor.

Called from POST /api/deals/match. Silent no-op if no flagged notes match:
the goal is informational, not blocking. Sender + carrier see the note in
their chat history the moment they land in the vault.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealVaultMessage
from app.models.marketplace import Trip
from app.models.notices import RouteNote, RouteStatus


_STATUS_LABEL = {
    RouteStatus.complex: "Сложный коридор",
    RouteStatus.restricted: "Ограниченный коридор",
    RouteStatus.attention: "Обратите внимание",
}


async def maybe_pin_route_note(db: AsyncSession, deal: Deal, trip: Trip) -> DealVaultMessage | None:
    """Fetch active flagged RouteNotes for the trip corridor and, if any exist,
    post a single pinned system-message summarising them into the vault.
    Returns the created message or None. Not committed — caller commits."""
    now = datetime.now(tz=timezone.utc)
    stmt = (
        select(RouteNote)
        .where(
            RouteNote.active_from <= now,
            or_(RouteNote.active_until.is_(None), RouteNote.active_until > now),
            RouteNote.status.in_(
                [RouteStatus.complex, RouteStatus.restricted, RouteStatus.attention]
            ),
            or_(RouteNote.origin_iso == trip.origin, RouteNote.origin_iso == "*"),
            or_(
                RouteNote.destination_iso == trip.destination,
                RouteNote.destination_iso == "*",
            ),
        )
    )
    notes = (await db.execute(stmt)).scalars().all()
    if not notes:
        return None

    lines: list[str] = ["📌 Информация о коридоре:"]
    for n in notes:
        label = _STATUS_LABEL.get(n.status, str(n.status))
        headline = n.headline or f"{n.origin_iso}→{n.destination_iso}"
        lines.append(f"• [{label}] {headline}")
        if n.body:
            lines.append(f"  {n.body}")

    msg = DealVaultMessage(
        deal_id=deal.id,
        sender_id=None,
        text="\n".join(lines),
        is_system=True,
    )
    db.add(msg)
    return msg
