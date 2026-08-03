"""T1.26 / T_UX.4 A — helpers for the receiving-address share flow.

Format of the shared address message is a *conventional prefix* pattern:
messages whose text starts with `SHARE_ADDRESS_PREFIX` are rendered by the
frontend as an address card. Backend does not enforce structure past that
prefix — we keep it as a plain `DealVaultMessage.text` so the message is
still fully searchable/exportable/append-only.

T_UX.4 A: address source is now `ReceivingAddress` (multiple per user).
`resolve_share_address` picks the requested one by id, or the default, and
falls back to the legacy `User.receiving_*` columns during the deprecation
window (users who haven't touched their profile after the migration).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import ReceivingAddress
from app.models.user import User

SHARE_ADDRESS_PREFIX = "📍 SHARED ADDRESS"


class AddressNotSetError(Exception):
    """User tried to share address but hasn't set one in profile."""


@dataclass
class _AddressView:
    label: str
    country_iso: str
    city: str | None
    street: str | None
    postal_code: str | None
    note: str | None


async def resolve_share_address(
    db: AsyncSession, user: User, address_id: uuid.UUID | None = None
) -> _AddressView:
    """Returns the address to share. Explicit `address_id` wins; then the
    default `ReceivingAddress`; then legacy `User.receiving_*` fields.
    Raises AddressNotSetError if nothing usable is set."""
    if address_id is not None:
        addr = await db.get(ReceivingAddress, address_id)
        if addr is None or addr.user_id != user.id:
            raise AddressNotSetError(f"Address {address_id} not found")
        return _view_from_row(addr)

    default = (
        await db.execute(
            select(ReceivingAddress)
            .where(ReceivingAddress.user_id == user.id)
            .where(ReceivingAddress.is_default.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if default is not None:
        return _view_from_row(default)

    # T_KEYS.1 (слой 4) — the `User.receiving_*` fallback is gone.
    #
    # It existed since T_UX.4 for accounts that filled the old single-address
    # fields and never got a row in `receiving_addresses`. Measured on prod
    # 2026-08-02: one account still carries the old columns, and it has a row
    # too — so the branch could not fire for anyone. Unreachable code in the
    # path that decides where a parcel is delivered is worth removing precisely
    # because it looks like a safety net and is not one.
    #
    # The columns themselves stay for now: dropping them is the contract phase
    # and reaches `MeOut`, `UserUpdate` and the frontend `User` type. Removing
    # the read first is safe on its own and makes that migration a pure delete.
    raise AddressNotSetError("No receiving address set")


def _view_from_row(addr: ReceivingAddress) -> _AddressView:
    return _AddressView(
        label=addr.label,
        country_iso=addr.country_iso,
        city=addr.city,
        street=addr.street,
        postal_code=addr.postal_code,
        note=addr.note,
    )


def format_address_message(view: _AddressView) -> str:
    """Build the multi-line text that gets stored as a DealVaultMessage."""
    lines = [SHARE_ADDRESS_PREFIX, f"Label: {view.label}"]
    lines.append(f"Country: {view.country_iso}")
    if view.city:
        lines.append(f"City: {view.city}")
    if view.street:
        lines.append(f"Street: {view.street}")
    if view.postal_code:
        lines.append(f"Postal: {view.postal_code}")
    if view.note:
        lines.append(f"Note: {view.note}")
    return "\n".join(lines)
