"""T1.26 — helpers for the receiving-address share flow.

Format of the shared address message is a *conventional prefix* pattern:
messages whose text starts with `SHARE_ADDRESS_PREFIX` are rendered by the
frontend as an address card. Backend does not enforce structure past that
prefix — we keep it as a plain `DealVaultMessage.text` so the message is
still fully searchable/exportable/append-only.
"""
from app.models.user import User

SHARE_ADDRESS_PREFIX = "📍 SHARED ADDRESS"


class AddressNotSetError(Exception):
    """User tried to share address but hasn't set one in profile."""


def format_address_message(user: User) -> str:
    """Build the multi-line text that gets stored as a DealVaultMessage."""
    if not user.receiving_country_iso:
        raise AddressNotSetError("receiving_country_iso is required")
    lines = [SHARE_ADDRESS_PREFIX]
    lines.append(f"Country: {user.receiving_country_iso}")
    if user.receiving_city:
        lines.append(f"City: {user.receiving_city}")
    if user.receiving_street:
        lines.append(f"Street: {user.receiving_street}")
    if user.receiving_postal_code:
        lines.append(f"Postal: {user.receiving_postal_code}")
    if user.receiving_note:
        lines.append(f"Note: {user.receiving_note}")
    return "\n".join(lines)
