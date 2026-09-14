"""T3.12.03 — what a cargo and its deals answer, computed rather than stored.

`D-CARGO-MODEL`: the cargo is one row through every deal it passes, and several
facts about it are **readings of those deals**, not columns — the deal's number,
where the cargo is now, whether it is a multi-hop, which deal is the last. A
stored copy of any of them would be a second answer to a question that already
has one, and the two would disagree on the day it mattered.

Functions (PROJECT §6.2a):
- `deal_no(shipment_no, position)` — the number of one deal.
  Called by: `api.deals.get_deal`, `api.deals.list_deals`.
- `cargo_location(status)` — where the cargo is, from its deal's status.
  Called by: `api.deals.get_deal`.
- `multihop_deal_count(db, cargo_id)` — how many deals make up the cargo's chain.
  Called by: `api.deals.get_deal`, `follow_recipient`.
- `is_last_deal(deal, cargo)` — the last deal is the one whose recipient is final.
  **No caller yet** (TECHSTATE §3a): it waits for the multi-hop mechanics.
- `follow_recipient(db, deal)` — keeps `final_recipient` in step for a single deal.
  Called by: `api.participants`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealStatus
from app.models.marketplace import Cargo

#: Owner's rule 2026-09-13: a multi-hop counts deals in active and finished
#: statuses. A cancelled deal plus a new one is not a chain — it is one attempt
#: that did not happen and one that did.
NOT_IN_CHAIN: tuple[DealStatus, ...] = (DealStatus.cancelled,)

#: Owner's three places for a cargo — on its way · with a courier or post ·
#: waiting at an address for the carrier — plus the end of the road. A cancelled
#: or disputed deal says nothing reliable about where the parcel is, so it
#: answers nothing rather than a guess.
_LOCATION: dict[DealStatus, str | None] = {
    DealStatus.draft: "awaiting_carrier",
    DealStatus.matched: "awaiting_carrier",
    DealStatus.accepted: "awaiting_carrier",
    DealStatus.in_transit: "in_transit",
    DealStatus.posted: "with_postal_service",
    DealStatus.delivered: "delivered",
    DealStatus.confirmed: "delivered",
    DealStatus.closed: "delivered",
    DealStatus.cancelled: None,
    DealStatus.disputed: None,
}


def deal_no(shipment_no: str | None, position: int) -> str | None:
    """`PF-482-19375` + position → `PF-482-19375-1`. A number issued before the
    format changed is shown as it is, without a suffix (owner, 2026-09-13)."""
    if not shipment_no:
        return None
    if shipment_no.startswith("PF-"):
        return f"{shipment_no}-{position}"
    return shipment_no


def cargo_location(status: DealStatus | str) -> str | None:
    return _LOCATION.get(DealStatus(status))


async def multihop_deal_count(db: AsyncSession, cargo_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count(Deal.id)).where(
                Deal.cargo_id == cargo_id,
                Deal.status.notin_(NOT_IN_CHAIN),
            )
        )
    ).scalar_one()


def is_last_deal(deal, cargo) -> bool:
    """Owner's rule 2026-09-13: «сделка последняя ⟺ её получатель совпадает с
    `Cargo.final_recipient`». Unknown final recipient answers no — a chain whose
    end nobody has named has no last deal yet."""
    return (
        cargo.final_recipient_id is not None
        and deal.recipient_id == cargo.final_recipient_id
    )


async def follow_recipient(db: AsyncSession, deal: Deal) -> None:
    """For a cargo carried by one deal, that deal's recipient **is** the final
    recipient, so the cargo follows it when the recipient is named, accepted or
    revoked. Once there is a chain the final recipient is the sender's answer
    and a middle deal must not overwrite it."""
    cargo = await db.get(Cargo, deal.cargo_id)
    if cargo is None:
        return
    if await multihop_deal_count(db, deal.cargo_id) <= 1:
        cargo.final_recipient_id = deal.recipient_id
