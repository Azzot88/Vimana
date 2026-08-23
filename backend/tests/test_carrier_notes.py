"""T_UX.21 — the carrier's two standing notes: how they work, how to pay them.

Both are free text on `users`, both are owner-only, and neither is copied onto
a trip the way `carriage_rules` is (T_UX.15). These tests hold those three
properties, because all three are easy to lose by accident: a field added to
`UserOut` instead of `MeOut` publishes a bank account, and a field wired into
the trip-creation path would freeze an answer time that is meant to stay
current.
"""
from __future__ import annotations

from app.schemas.user import UserOut


async def test_both_notes_round_trip(client, carrier_headers):
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={
            "interaction_rules": "I answer within 3 hours.",
            "payment_instructions": "Cash on handover, or IBAN on request.",
        },
    )
    assert r.status_code == 200, r.text

    mine = await client.get("/api/auth/me", headers=carrier_headers)
    assert mine.status_code == 200, mine.text
    body = mine.json()
    assert body["interaction_rules"] == "I answer within 3 hours."
    assert body["payment_instructions"] == "Cash on handover, or IBAN on request."


async def test_interaction_rules_over_the_limit_is_refused(client, carrier_headers):
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"interaction_rules": "x" * 4001},
    )
    assert r.status_code == 422


async def test_payment_instructions_over_the_limit_is_refused(client, carrier_headers):
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"payment_instructions": "x" * 4001},
    )
    assert r.status_code == 422


async def test_editing_one_note_leaves_the_other(client, carrier_headers):
    """`exclude_unset`, held by a test because the screen saves one box at a
    time: if a partial write ever started assigning the whole model, saving the
    answer time would silently erase the payment details."""
    await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={
            "interaction_rules": "Send a passport scan first.",
            "payment_instructions": "Revolut.",
        },
    )
    r = await client.patch(
        "/api/auth/me",
        headers=carrier_headers,
        json={"interaction_rules": "Send a passport scan and the address."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["payment_instructions"] == "Revolut."


def test_notes_are_not_on_the_public_view():
    """The one that would hurt: `UserOut` is what a counterparty and the public
    identity page read. Payment details on it would be published to anyone who
    opened a profile, and nothing in the UI would look wrong."""
    assert "payment_instructions" not in UserOut.model_fields
    assert "interaction_rules" not in UserOut.model_fields
