"""T3.3 / T3.12.05 — the recipient: offered, answered, and only then a role.

Owner, 2026-09-14: «роль предлагается, а не назначается» — rights do not arrive
before the answer. What is pinned is exactly that: an offer — by link or to a
person — gives nothing; acceptance gives the deal; a refusal can stop the next
offer; one offer at a time; and the sender can take it all back.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from tests.conftest import make_account


async def _register(client, prefix: str, *, carrier: bool = False):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email(prefix)
    payload = {"email": email, "password": SEED_PASSWORD, "display_name": prefix.upper()}
    if carrier:
        payload.update({"can_carry": True, "active_mode": "carrier"})
    await make_account(payload)
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, email


@pytest.fixture
async def _deal(client):
    """Sender + carrier + matched deal."""
    c_hdr, _ = await _register(client, "r-c", carrier=True)
    s_hdr, _ = await _register(client, "r-s")
    trip = await client.post(
        "/api/trips",
        headers=c_hdr,
        json={
            "payment_model": "cash_on_delivery",
            "segments": [
                {
                    "origin": "RCP",
                    "destination": "DST",
                    "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                }
            ],
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    match = await client.post(
        "/api/deals/match",
        headers=s_hdr,
        json={
            "trip_id": trip.json()["id"],
            "cargo": {
                "weight_kg": 1.0,
                "category": "document",
                "declared_value": 50.0,
            },
        },
    )
    return {"sender_headers": s_hdr, "carrier_headers": c_hdr, "deal_id": match.json()["id"]}


async def _me(client, hdr) -> str:
    return (await client.get("/api/auth/me", headers=hdr)).json()["id"]


async def _offer(client, _deal, user_id):
    return await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient-offers",
        headers=_deal["sender_headers"],
        json={"user_id": user_id},
    )


async def _offer_id(client, hdr, deal_id) -> str:
    offers = (await client.get("/api/me/recipient-offers", headers=hdr)).json()
    return next(o["id"] for o in offers if o["deal_id"] == deal_id)


async def _link(client, _deal) -> str:
    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    assert inv.status_code == 201, inv.text
    return inv.json()["invite_token"]


async def _recipient(client, _deal, prefix: str):
    """A person offered the role and accepting it — the only way in."""
    hdr, _ = await _register(client, prefix)
    user_id = await _me(client, hdr)
    offered = await _offer(client, _deal, user_id)
    assert offered.status_code == 201, offered.text
    accepted = await client.post(
        f"/api/recipient-offers/{await _offer_id(client, hdr, _deal['deal_id'])}/accept",
        headers=hdr,
    )
    assert accepted.status_code == 200, accepted.text
    return hdr, user_id


async def _deal_visible(client, hdr, deal_id) -> bool:
    detail = await client.get(f"/api/deals/{deal_id}", headers=hdr)
    page = await client.get("/api/deals", headers=hdr, params={"limit": 100})
    listed = deal_id in {d["id"] for d in page.json()["items"]}
    return detail.status_code == 200 and listed


# ── the link ──────────────────────────────────────────────────────────────


async def test_only_sender_can_invite(client, _deal):
    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["carrier_headers"],
    )
    assert r.status_code == 403


async def test_invite_returns_token_and_url(client, _deal):
    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["invite_token"]) > 20
    assert body["invite_url"].endswith(body["invite_token"])
    assert body["role"] == "recipient"


async def test_a_link_finds_its_person_and_gives_them_nothing(client, _deal):
    """Opening the link used to be the acceptance. Now it shows the offer —
    route, sender — and the deal stays closed until the answer."""
    token = await _link(client, _deal)
    hdr, _ = await _register(client, "r-link")

    claimed = await client.post(f"/api/deals/join/{token}", headers=hdr)
    assert claimed.status_code == 200, claimed.text
    offer = claimed.json()
    assert offer["state"] == "pending"
    assert offer["route"] == "RCP → DST"
    assert offer["sender_name"] == "R-S"

    assert not await _deal_visible(client, hdr, _deal["deal_id"])
    vault = await client.get(f"/api/deals/{_deal['deal_id']}/dealvault", headers=hdr)
    assert vault.status_code == 403


async def test_accepting_the_link_makes_them_the_recipient(client, _deal):
    token = await _link(client, _deal)
    hdr, _ = await _register(client, "r-yes")
    offer_id = (await client.post(f"/api/deals/join/{token}", headers=hdr)).json()["id"]

    accepted = await client.post(f"/api/recipient-offers/{offer_id}/accept", headers=hdr)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "accepted"

    detail = await client.get(f"/api/deals/{_deal['deal_id']}", headers=hdr)
    assert detail.status_code == 200, detail.text
    assert detail.json()["recipient_id"] == await _me(client, hdr)
    assert detail.json()["recipient_name"] == "R-YES"


async def test_claiming_twice_is_the_same_offer(client, _deal):
    token = await _link(client, _deal)
    hdr, _ = await _register(client, "r-idem")
    a = await client.post(f"/api/deals/join/{token}", headers=hdr)
    b = await client.post(f"/api/deals/join/{token}", headers=hdr)
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] == b.json()["id"]


async def test_a_link_belongs_to_one_person(client, _deal):
    token = await _link(client, _deal)
    rec1, _ = await _register(client, "r-conf-1")
    rec2, _ = await _register(client, "r-conf-2")
    await client.post(f"/api/deals/join/{token}", headers=rec1)
    r2 = await client.post(f"/api/deals/join/{token}", headers=rec2)
    assert r2.status_code == 409


async def test_deal_principals_cant_take_the_link(client, _deal):
    token = await _link(client, _deal)
    resp = await client.post(f"/api/deals/join/{token}", headers=_deal["carrier_headers"])
    assert resp.status_code == 400


# ── an offer to a person ──────────────────────────────────────────────────


async def test_an_offer_waits_for_the_person_s_answer(client, _deal):
    hdr, _ = await _register(client, "r-wait")
    user_id = await _me(client, hdr)

    offered = await _offer(client, _deal, user_id)
    assert offered.status_code == 201, offered.text
    assert offered.json()["state"] == "pending"
    assert offered.json()["accepted_at"] is None

    sender_view = await client.get(
        f"/api/deals/{_deal['deal_id']}", headers=_deal["sender_headers"]
    )
    assert sender_view.json()["recipient_id"] is None
    assert not await _deal_visible(client, hdr, _deal["deal_id"])

    offers = (await client.get("/api/me/recipient-offers", headers=hdr)).json()
    assert [o["deal_id"] for o in offers] == [_deal["deal_id"]]


async def test_declining_gives_nothing_and_can_refuse_the_next_offer(client, _deal):
    """«Отказавшийся может запретить назначать себя получателем» — enforced by
    the API, for offers by person and by link alike."""
    hdr, _ = await _register(client, "r-no")
    user_id = await _me(client, hdr)
    await _offer(client, _deal, user_id)
    offer_id = await _offer_id(client, hdr, _deal["deal_id"])

    declined = await client.post(
        f"/api/recipient-offers/{offer_id}/decline",
        headers=hdr,
        json={"refuse_future": True},
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["state"] == "declined"
    assert not await _deal_visible(client, hdr, _deal["deal_id"])
    assert (await client.get("/api/auth/me", headers=hdr)).json()["refuses_recipient_offers"] is True

    again = await _offer(client, _deal, user_id)
    assert again.status_code == 403, again.text

    token = await _link(client, _deal)
    by_link = await client.post(f"/api/deals/join/{token}", headers=hdr)
    assert by_link.status_code == 403, by_link.text


async def test_the_setting_refuses_offers_before_any_arrive(client, _deal):
    hdr, _ = await _register(client, "r-pref")
    set_ = await client.patch(
        "/api/auth/me", headers=hdr, json={"refuses_recipient_offers": True}
    )
    assert set_.status_code == 200, set_.text
    r = await _offer(client, _deal, await _me(client, hdr))
    assert r.status_code == 403


async def test_a_new_offer_withdraws_the_unanswered_one(client, _deal):
    first, _ = await _register(client, "r-one")
    second, _ = await _register(client, "r-two")
    await _offer(client, _deal, await _me(client, first))
    first_offer = await _offer_id(client, first, _deal["deal_id"])
    await _offer(client, _deal, await _me(client, second))

    stale = await client.post(f"/api/recipient-offers/{first_offer}/accept", headers=first)
    assert stale.status_code == 409, stale.text
    fresh = await client.post(
        f"/api/recipient-offers/{await _offer_id(client, second, _deal['deal_id'])}/accept",
        headers=second,
    )
    assert fresh.status_code == 200, fresh.text


async def test_no_new_offer_while_somebody_holds_the_role(client, _deal):
    await _recipient(client, _deal, "r-holds")
    other, _ = await _register(client, "r-next")

    assert (await _offer(client, _deal, await _me(client, other))).status_code == 409
    link = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    assert link.status_code == 409

    withdrawn = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient/withdraw",
        headers=_deal["sender_headers"],
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert (await _offer(client, _deal, await _me(client, other))).status_code == 201


async def test_nobody_answers_somebody_else_s_offer(client, _deal):
    hdr, _ = await _register(client, "r-mine")
    await _offer(client, _deal, await _me(client, hdr))
    offer_id = await _offer_id(client, hdr, _deal["deal_id"])
    stranger, _ = await _register(client, "r-thief")

    for action in ("accept", "decline"):
        r = await client.post(f"/api/recipient-offers/{offer_id}/{action}", headers=stranger)
        assert r.status_code == 404, (action, r.text)


async def test_unknown_key_says_so_instead_of_inviting(client, _deal):
    """A key nobody holds must not quietly become an invitation."""
    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient-offers",
        headers=_deal["sender_headers"],
        json={"npub": "f" * 64},
    )
    assert r.status_code == 404
    assert "invite" in r.json()["detail"].lower()


async def test_an_offer_needs_exactly_one_identifier(client, _deal):
    both = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient-offers",
        headers=_deal["sender_headers"],
        json={"user_id": str(_deal["deal_id"]), "npub": "a" * 64},
    )
    assert both.status_code == 422
    neither = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient-offers",
        headers=_deal["sender_headers"],
        json={},
    )
    assert neither.status_code == 422


async def test_only_sender_can_offer_the_role(client, _deal):
    hdr, _ = await _register(client, "r-outsider")
    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient-offers",
        headers=_deal["carrier_headers"],
        json={"user_id": await _me(client, hdr)},
    )
    assert r.status_code == 403


async def test_carrier_cannot_be_offered_the_role(client, _deal):
    r = await _offer(client, _deal, await _me(client, _deal["carrier_headers"]))
    assert r.status_code == 400


# ── the role ──────────────────────────────────────────────────────────────


async def test_recipient_can_read_and_write_chat(client, _deal):
    rec_hdr, _ = await _recipient(client, _deal, "r-chat")

    s_msg = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages",
        headers=_deal["sender_headers"],
        json={"text": "sender says hi"},
    )
    assert s_msg.status_code == 201

    r_list = await client.get(f"/api/deals/{_deal['deal_id']}/dealvault", headers=rec_hdr)
    assert r_list.status_code == 200
    assert "sender says hi" in [m["text"] for m in r_list.json()["items"]]

    r_msg = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages",
        headers=rec_hdr,
        json={"text": "recipient reply"},
    )
    assert r_msg.status_code == 201


async def test_the_recipient_finds_the_deal_in_their_list(client, _deal):
    hdr, _ = await _recipient(client, _deal, "r-list")
    page = await client.get("/api/deals", headers=hdr, params={"limit": 100})
    rows = [d for d in page.json()["items"] if d["id"] == _deal["deal_id"]]
    assert len(rows) == 1
    assert rows[0]["recipient_name"] == "R-LIST"


async def test_the_sender_s_list_names_the_recipient_too(client, _deal):
    await _recipient(client, _deal, "r-named2")
    page = await client.get(
        "/api/deals", headers=_deal["sender_headers"], params={"limit": 100}
    )
    rows = [d for d in page.json()["items"] if d["id"] == _deal["deal_id"]]
    assert rows and rows[0]["recipient_name"] == "R-NAMED2"


async def test_withdrawing_closes_the_deal_to_the_recipient(client, _deal):
    hdr, _ = await _recipient(client, _deal, "r-gone")

    rev = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient/withdraw",
        headers=_deal["sender_headers"],
    )
    assert rev.status_code == 200, rev.text

    assert not await _deal_visible(client, hdr, _deal["deal_id"])
    vault = await client.get(f"/api/deals/{_deal['deal_id']}/dealvault", headers=hdr)
    assert vault.status_code == 403
    detail = await client.get(
        f"/api/deals/{_deal['deal_id']}", headers=_deal["sender_headers"]
    )
    assert detail.json()["recipient_id"] is None


async def test_only_sender_withdraws(client, _deal):
    await _recipient(client, _deal, "r-rev2")
    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient/withdraw",
        headers=_deal["carrier_headers"],
    )
    assert r.status_code == 403


async def test_participants_are_listed_to_the_deal_s_people_only(client, _deal):
    pending_hdr, _ = await _register(client, "r-pend")
    await _offer(client, _deal, await _me(client, pending_hdr))

    s_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/participants", headers=_deal["sender_headers"]
    )
    assert s_list.status_code == 200
    assert [p["state"] for p in s_list.json()] == ["pending"]
    # Offered is not a participant yet.
    mine = await client.get(f"/api/deals/{_deal['deal_id']}/participants", headers=pending_hdr)
    assert mine.status_code == 403

    await client.post(
        f"/api/recipient-offers/{await _offer_id(client, pending_hdr, _deal['deal_id'])}/accept",
        headers=pending_hdr,
    )
    c_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/participants", headers=_deal["carrier_headers"]
    )
    assert [p["state"] for p in c_list.json()] == ["accepted"]
    r_list = await client.get(f"/api/deals/{_deal['deal_id']}/participants", headers=pending_hdr)
    assert r_list.status_code == 200

    other_hdr, _ = await _register(client, "r-out")
    o_list = await client.get(f"/api/deals/{_deal['deal_id']}/participants", headers=other_hdr)
    assert o_list.status_code == 403


# ── T3.12.05 pt.2 · the sender at the other end, and what the recipient can do ─


async def test_the_sender_can_be_their_own_recipient(client, _deal):
    """«Получатель — я» needs no offer — nobody is being asked anything — and
    the sender still reads the deal as the sender."""
    named = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient/self", headers=_deal["sender_headers"]
    )
    assert named.status_code == 200, named.text
    detail = await client.get(
        f"/api/deals/{_deal['deal_id']}", headers=_deal["sender_headers"]
    )
    assert detail.json()["recipient_id"] == await _me(client, _deal["sender_headers"])

    # One recipient: somebody else is not offered the role over it.
    other, _ = await _register(client, "r-over-self")
    assert (await _offer(client, _deal, await _me(client, other))).status_code == 409
    withdrawn = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient/withdraw",
        headers=_deal["sender_headers"],
    )
    assert withdrawn.status_code == 200
    assert (await _offer(client, _deal, await _me(client, other))).status_code == 201


async def test_only_the_sender_names_themselves(client, _deal):
    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/recipient/self", headers=_deal["carrier_headers"]
    )
    assert r.status_code == 403


def test_cards_for_the_recipient_go_to_a_sender_who_is_one():
    """Otherwise a delivery addressed to the recipient would wait for a role
    nobody can act as — the sender reads the deal as the sender."""
    from types import SimpleNamespace

    from app.core.cards import CATALOGUE, CardKind, resolve_ack_role
    from app.models.deal import CardAckRole

    spec = CATALOGUE[CardKind.delivery_declared]
    self_deal = SimpleNamespace(sender_id="s", carrier_id="c", recipient_id="s")
    other_deal = SimpleNamespace(sender_id="s", carrier_id="c", recipient_id="r")
    assert resolve_ack_role(spec, self_deal, CardAckRole.carrier) is CardAckRole.sender
    assert resolve_ack_role(spec, other_deal, CardAckRole.carrier) is CardAckRole.recipient


async def test_the_recipient_asks_the_sender_to_open_a_dispute(client, _deal):
    """The recipient does not open a dispute (owner, 2026-09-13); they ask the
    sender to, and the request is a line the sender reads — nobody answers it
    (owner, 2026-09-14)."""
    rec_hdr, _ = await _recipient(client, _deal, "r-asks")

    asked = await client.post(
        f"/api/deals/{_deal['deal_id']}/cards",
        headers=rec_hdr,
        json={"kind": "dispute.requested", "payload": {"reason": "damaged"}, "text": "the box is wet"},
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["card_kind"] == "dispute.requested"
    assert asked.json()["requires_ack_by"] is None

    for hdr in (_deal["sender_headers"], _deal["carrier_headers"]):
        r = await client.post(
            f"/api/deals/{_deal['deal_id']}/cards",
            headers=hdr,
            json={"kind": "dispute.requested", "payload": {"reason": "damaged"}},
        )
        assert r.status_code == 403, r.text

    seen = await client.get(
        f"/api/deals/{_deal['deal_id']}/dealvault", headers=_deal["sender_headers"]
    )
    assert "dispute.requested" in {m["card_kind"] for m in seen.json()["items"]}
    # And the recipient still cannot open one themselves.
    direct = await client.post(
        f"/api/deals/{_deal['deal_id']}/dispute",
        headers=rec_hdr,
        json={"reason": "other", "details": "trying the door anyway"},
    )
    assert direct.status_code == 403


async def test_the_recipient_moves_the_delivery_and_the_carrier_answers(client, _deal):
    """«Получатель меняет условия встречи и вручения, подтверждает перевозчик,
    отправитель видит это в чате»."""
    rec_hdr, _ = await _recipient(client, _deal, "r-moves")

    # T_UX.29 п.4 — the carrier names the delivery first; the recipient's card is
    # a change to it. Before anything is named there is nothing to move, and the
    # server says so with a 403.
    too_early = await client.post(
        f"/api/deals/{_deal['deal_id']}/cards",
        headers=rec_hdr,
        json={"kind": "dropoff.proposed", "payload": {"method": "in_person", "city": "Queens"}},
    )
    assert too_early.status_code == 403, too_early.text

    named = await client.post(
        f"/api/deals/{_deal['deal_id']}/cards",
        headers=_deal["carrier_headers"],
        json={"kind": "dropoff.proposed", "payload": {"method": "in_person", "city": "Brooklyn"}},
    )
    assert named.status_code == 201, named.text

    proposed = await client.post(
        f"/api/deals/{_deal['deal_id']}/cards",
        headers=rec_hdr,
        json={"kind": "dropoff.proposed", "payload": {"method": "in_person", "city": "Queens"}},
    )
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["requires_ack_by"] == "carrier"

    by_sender = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages/{proposed.json()['id']}/ack",
        headers=_deal["sender_headers"],
        json={"decision": "accepted"},
    )
    assert by_sender.status_code == 403
    by_carrier = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages/{proposed.json()['id']}/ack",
        headers=_deal["carrier_headers"],
        json={"decision": "accepted"},
    )
    assert by_carrier.status_code == 200, by_carrier.text

    # T_UX.29 п.7 — and the proposal it overtook is not still waiting for an
    # answer. Two live «Принять · Отклонить» over one meeting is what left a
    # settled arrangement answerable, and answering would have moved it back.
    assert proposed.json()["supersedes_id"] == named.json()["id"]
    listing = await client.get(
        f"/api/deals/{_deal['deal_id']}/dealvault", headers=rec_hdr
    )
    states = {
        m["id"]: m["card_state"] for m in listing.json()["items"] if m.get("card_kind")
    }
    assert states[named.json()["id"]] == "superseded"

    seen = await client.get(
        f"/api/deals/{_deal['deal_id']}/dealvault", headers=_deal["sender_headers"]
    )
    assert proposed.json()["id"] in {m["id"] for m in seen.json()["items"]}


async def test_decrypt_for_me_endpoint_returns_plaintext_for_recipient_of_e2e_message(
    client, _deal, session_maker
):
    """Full e2e roundtrip: sender publishes e2e-message with recipient's read_pkg.
    Recipient calls server-mediated decrypt endpoint → gets plaintext."""
    import base64
    import os as _os

    from app.core.threshold import nip44_encrypt
    from app.models.deal import Deal
    from app.models.user import User

    rec_hdr, recipient_uid = await _recipient(client, _deal, "r-dec")

    async with session_maker() as db:
        deal = await db.get(Deal, _deal["deal_id"])
        sender = await db.get(User, deal.sender_id)
        carrier = await db.get(User, deal.carrier_id)
        recipient = await db.get(User, recipient_uid)
        recipient_id = recipient.id
        sender_npub = sender.nostr_pubkey
        carrier_npub = carrier.nostr_pubkey
        recipient_npub = recipient.nostr_pubkey
        # The sender stays custodial — this suite exercises the server-mediated
        # read. The test encrypts on their behalf with the service key, read the
        # way the platform reads it (T3.12: `export` is gone; it handed the user
        # a key that was never theirs).
        from app.core.keypair import decrypt_nsec

        sender_nsec = decrypt_nsec(
            bytes(sender.nsec_nonce), bytes(sender.nsec_encrypted)
        )

    session_key = _os.urandom(32)
    fake_nonce = _os.urandom(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ciphertext = AESGCM(session_key).encrypt(fake_nonce, b"hello recipient", None)

    payload = {
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "nonce": base64.b64encode(fake_nonce).decode("ascii"),
        "wrapped_shares": {
            "sender": nip44_encrypt(b"\x01" + session_key, sender_nsec, sender_npub),
            "carrier": nip44_encrypt(b"\x02" + session_key, sender_nsec, carrier_npub),
            "arbiter": nip44_encrypt(b"\x03" + session_key, sender_nsec, sender_npub),  # no real arbiter — reuse sender npub for shape only
        },
        "read_packages": {
            "sender": nip44_encrypt(session_key, sender_nsec, sender_npub),
            "carrier": nip44_encrypt(session_key, sender_nsec, carrier_npub),
            f"recipient_{recipient_id}": nip44_encrypt(
                session_key, sender_nsec, recipient_npub
            ),
        },
    }

    msg_r = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages",
        headers=_deal["sender_headers"],
        json={"e2e_payload": payload},
    )
    assert msg_r.status_code == 201, msg_r.json()
    msg_id = msg_r.json()["id"]

    dec = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages/{msg_id}/decrypt-for-me",
        headers=rec_hdr,
    )
    assert dec.status_code == 200, dec.json()
    assert dec.json()["text"] == "hello recipient"
