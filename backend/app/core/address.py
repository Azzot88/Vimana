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

    # Legacy fallback — user filled the old fields but never migrated to
    # multiple addresses.
    if user.receiving_country_iso:
        return _AddressView(
            label="Default",
            country_iso=user.receiving_country_iso,
            city=user.receiving_city,
            street=user.receiving_street,
            postal_code=user.receiving_postal_code,
            note=user.receiving_note,
        )

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
