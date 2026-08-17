"""T3.34 — typed cards in the vault.

Two things are worth testing here and one is not. Not worth it: that a column
stores what was written to it. Worth it: that the *type* now lives in the field
rather than the text, and that answering a card is refused on the server when
the wrong side asks — the rule the UI can only decorate (§6.9.5 п.6).
"""
from __future__ import annotations

import uuid

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _set_receiving_address(client, headers) -> None:
    await client.post(
        "/api/me/addresses",
        headers=headers,
        json={
            "label": "Home",
            "country_iso": "AE",
            "city": "Dubai",
            "street": "Marina Walk",
        },
    )


async def _make_card(session_maker, deal_id, *, kind, ack_role, state="pending"):
    """Insert a card directly.

    Cards other than `address.shared` have no creation endpoint until T3.35+,
    and waiting for one would mean not testing the ack rule at all.
    """
    from app.models.deal import CardAckRole, CardState, DealVaultMessage

    async with session_maker() as db:
        msg = DealVaultMessage(
            deal_id=deal_id,
            sender_id=None,
            text=None,
            is_system=True,
            card_kind=kind,
            card_state=CardState(state),
            requires_ack_by=CardAckRole(ack_role) if ack_role else None,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg.id


# ── the catalogue ─────────────────────────────────────────────────────────


def test_every_kind_has_a_spec():
    """A kind declared without a spec is a card nothing can validate."""
    from app.core.cards import CATALOGUE, CardKind

    for kind in CardKind:
        assert kind in CATALOGUE, kind


def test_spec_for_rejects_unknown_string():
    from app.core.cards import spec_for

    assert spec_for("terms.proposed") is not None
    assert spec_for("not.a.card") is None


def test_implemented_kinds_are_reachable():
    """`implemented` has to mean something, and "exactly one kind" stopped
    being that the moment T3.36–T3.39 landed. The property that survives: a
    kind marked implemented must be producible by somebody — a role may raise
    it, the server emits it as the other half of a two-sided step, or it has a
    dedicated endpoint (terms and the shared address).
    """
    from app.core.cards import CATALOGUE, CardKind

    emitted = {s.on_accept_emit for s in CATALOGUE.values() if s.on_accept_emit}
    dedicated = {CardKind.address_shared} | {
        k for k in CardKind if k.value.startswith("terms.")
    }

    for kind, spec in CATALOGUE.items():
        if not spec.implemented:
            continue
        assert (
            spec.creator_roles or kind in emitted or kind in dedicated
        ), f"{kind} is marked implemented but nothing can produce it"


def test_unimplemented_kinds_cannot_be_raised():
    """The other direction: a kind nobody may create must not claim to be
    implemented, or the catalogue starts describing wishes."""
    from app.core.cards import CATALOGUE

    for kind, spec in CATALOGUE.items():
        if spec.creator_roles:
            assert spec.implemented, f"{kind} is creatable but not marked implemented"


# ── the type is a field now ───────────────────────────────────────────────


async def test_shared_address_is_typed(client, sender_headers, seed_deal):
    """T1.26 wrote the type into the message text as a prefix. It is a column
    now, and the text is left alone so the card still renders from it."""
    await _set_receiving_address(client, sender_headers)
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/share-address",
        headers=sender_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["card_kind"] == "address.shared"
    assert body["is_system"] is True
    # The address still travels in the text — only recognition moved.
    assert body["text"] and "SHARED ADDRESS" in body["text"]


async def test_plain_message_has_no_card_kind(client, sender_headers, seed_deal):
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "just a message", "is_system": False},
    )
    assert r.status_code == 201
    assert r.json()["card_kind"] is None
    assert r.json()["card_state"] is None


async def test_listing_exposes_the_envelope(client, sender_headers, seed_deal):
    """The client picks a renderer from the type and shows "awaiting answer"
    from the state — both have to survive the list endpoint."""
    r = await client.get(
        f"/api/deals/{seed_deal.id}/dealvault", headers=sender_headers
    )
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert "card_kind" in item
        assert "card_state" in item
        assert "requires_ack_by" in item


# ── answering a card ──────────────────────────────────────────────────────


async def test_ack_by_the_awaited_side_succeeds(
    client, carrier_headers, seed_deal, session_maker
):
    # `pickup.proposed` on purpose: `handoff.declared` needs a photo before it
    # can be confirmed (T3.37), and this test is about the answer, not the
    # evidence.
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="pickup.proposed", ack_role="carrier"
    )
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["card_state"] == "accepted"
    assert r.json()["acked_by_id"] is not None
    assert r.json()["acked_at"] is not None


async def test_decline_is_recorded_as_such(
    client, carrier_headers, seed_deal, session_maker
):
    """Declining is an outcome, not the absence of accepting — the record has
    to show that somebody said no."""
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="handoff.declared", ack_role="carrier"
    )
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "declined"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["card_state"] == "declined"


async def test_ack_by_the_wrong_side_is_refused(
    client, sender_headers, seed_deal, session_maker
):
    """The rule lives here. Hiding the button is decoration."""
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="handoff.declared", ack_role="carrier"
    )
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=sender_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 403, r.text


async def test_second_ack_conflicts(
    client, carrier_headers, seed_deal, session_maker
):
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="pickup.proposed", ack_role="carrier"
    )
    first = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "declined"},
    )
    assert second.status_code == 409, second.text


async def test_ack_on_a_plain_message_is_refused(
    client, sender_headers, seed_deal
):
    created = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "not a card", "is_system": False},
    )
    msg_id = created.json()["id"]
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=sender_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 422, r.text


async def test_ack_on_informational_card_is_refused(
    client, sender_headers, seed_deal, session_maker
):
    """Nobody owes an answer to a shared address."""
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="address.shared", ack_role=None
    )
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=sender_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 422, r.text


async def test_unknown_card_kind_is_refused(
    client, carrier_headers, seed_deal, session_maker
):
    """A row written by a version that knew a kind this one does not."""
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="from.the.future", ack_role="carrier"
    )
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 422, r.text


async def test_bad_decision_value_is_refused(
    client, carrier_headers, seed_deal, session_maker
):
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="handoff.declared", ack_role="carrier"
    )
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=carrier_headers,
        json={"decision": "maybe"},
    )
    assert r.status_code == 422, r.text


async def test_ack_missing_message_is_404(client, carrier_headers, seed_deal):
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{uuid.uuid4()}/ack",
        headers=carrier_headers,
        json={"decision": "accepted"},
    )
    assert r.status_code == 404, r.text


async def test_outsider_cannot_ack(client, seed_deal, session_maker):
    msg_id = await _make_card(
        session_maker, seed_deal.id, kind="handoff.declared", ack_role="carrier"
    )
    email = unique_email("outsider")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Outsider"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/ack",
        headers=hdr,
        json={"decision": "accepted"},
    )
    assert r.status_code in (403, 404), r.text
