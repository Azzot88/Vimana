"""T3.12.01 — who a person is in a deal, answered in one place.

Until now every endpoint kept its own list. `api/deals` knew the sender and the
carrier; `api/dealvault` also knew an invited recipient; `api/admin` knew the
first two. So the recipient could read the vault of a deal whose card, whose
list and whose arbiter guard did not know they existed — and the deal stuck at
delivery, because the server addressed the confirmation to somebody no screen
was drawn for (разбор 2026-09-13).

**Order matters.** A sender who named themselves the recipient answers
`sender`: that is the role that owes decisions, and `core.cards.role_of` reads
the deal the same way.

**Two sources for the recipient, on purpose.** `Deal.recipient_id` is what the
rest of the deal reads; an active `DealParticipant` row is how an invited reader
got in. Both paths now write both (`api.participants`), and revoking clears
both, so they agree — but a vault is not closed to somebody who holds only one
of them because a row predates the other.

Functions (PROJECT §6.2a):
- `party_role(db, deal, user_id)` — `sender` | `carrier` | `recipient` | None.
  Called by: `api.deals.get_deal`, `api.admin.claim_dispute`,
  `api.dealvault._get_deal_as_participant`.
- `recipient_deal_ids(user_id)` — subquery of the deals a person reads as an
  active participant. Called by: `api.deals.list_deals`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealParticipant


async def party_role(
    db: AsyncSession, deal: Deal, user_id: uuid.UUID
) -> str | None:
    if deal.sender_id == user_id:
        return "sender"
    if deal.carrier_id == user_id:
        return "carrier"
    if deal.recipient_id is not None and deal.recipient_id == user_id:
        return "recipient"
    row = (
        await db.execute(
            select(DealParticipant.id).where(
                DealParticipant.deal_id == deal.id,
                DealParticipant.user_id == user_id,
                *_ACCEPTED,
            )
        )
    ).first()
    return "recipient" if row is not None else None


#: T3.12.05 — only an accepted offer is a role (owner, 2026-09-14): «роль
#: предлагается, а не назначается». A pending, declined or revoked row gives
#: nothing — not the deal, not its list, not its vault.
_ACCEPTED = (
    DealParticipant.accepted_at.is_not(None),
    DealParticipant.declined_at.is_(None),
    DealParticipant.revoked_at.is_(None),
)


def recipient_deal_ids(user_id: uuid.UUID):
    return select(DealParticipant.deal_id).where(
        DealParticipant.user_id == user_id,
        *_ACCEPTED,
    )
