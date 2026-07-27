"""T3.3 — Recipient role: invite, join, revoke, list, chat access."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


async def _register(client, prefix: str, *, carrier: bool = False):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email(prefix)
    payload = {"email": email, "password": SEED_PASSWORD, "display_name": prefix.upper()}
    if carrier:
        payload.update({"can_carry": True, "active_mode": "carrier"})
    await client.post("/api/auth/register", json=payload)
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
            "origin": "RCP",
            "destination": "DST",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    match = await client.post(
        "/api/deals/match",
        headers=s_hdr,
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000001111",
                "origin": "RCP",
                "destination": "DST",
                "category": "document",
                "declared_value": 50.0,
            },
        },
    )
    return {"sender_headers": s_hdr, "carrier_headers": c_hdr, "deal_id": match.json()["id"]}


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


async def test_join_attaches_current_user(client, _deal, session_maker):
    from sqlalchemy import select

    from app.models.deal import DealParticipant

    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]

    rec_hdr, _ = await _register(client, "r-rec")
    join = await client.post(f"/api/deals/join/{token}", headers=rec_hdr)
    assert join.status_code == 200
    assert join.json()["role"] == "recipient"

    async with session_maker() as db:
        row = (
            await db.execute(
                select(DealParticipant).where(DealParticipant.invite_token == token)
            )
        ).scalar_one()
        assert row.user_id is not None
        assert row.accepted_at is not None


async def test_join_idempotent_for_same_user(client, _deal):
    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec_hdr, _ = await _register(client, "r-idem")
    a = await client.post(f"/api/deals/join/{token}", headers=rec_hdr)
    b = await client.post(f"/api/deals/join/{token}", headers=rec_hdr)
    assert a.status_code == 200 and b.status_code == 200


async def test_join_conflict_for_different_user(client, _deal):
    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec1, _ = await _register(client, "r-conf-1")
    rec2, _ = await _register(client, "r-conf-2")
    await client.post(f"/api/deals/join/{token}", headers=rec1)
    r2 = await client.post(f"/api/deals/join/{token}", headers=rec2)
    assert r2.status_code == 409


async def test_deal_principals_cant_join_as_recipient(client, _deal):
    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    resp = await client.post(f"/api/deals/join/{token}", headers=_deal["carrier_headers"])
    assert resp.status_code == 400


async def test_recipient_can_read_and_write_chat(client, _deal):
    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec_hdr, _ = await _register(client, "r-chat")
    await client.post(f"/api/deals/join/{token}", headers=rec_hdr)

    # Sender writes.
    s_msg = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages",
        headers=_deal["sender_headers"],
        json={"text": "sender says hi"},
    )
    assert s_msg.status_code == 201

    # Recipient reads.
    r_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/dealvault", headers=rec_hdr
    )
    assert r_list.status_code == 200
    texts = [m["text"] for m in r_list.json()["items"]]
    assert "sender says hi" in texts

    # Recipient writes.
    r_msg = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages",
        headers=rec_hdr,
        json={"text": "recipient reply"},
    )
    assert r_msg.status_code == 201


async def test_revoke_blocks_further_access(client, _deal, session_maker):
    from sqlalchemy import select

    from app.models.deal import DealParticipant

    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec_hdr, _ = await _register(client, "r-rev")
    await client.post(f"/api/deals/join/{token}", headers=rec_hdr)

    async with session_maker() as db:
        row = (
            await db.execute(
                select(DealParticipant).where(DealParticipant.invite_token == token)
            )
        ).scalar_one()
        recipient_uid = row.user_id

    # Sender revokes.
    rev = await client.post(
        f"/api/deals/{_deal['deal_id']}/participants/{recipient_uid}/revoke",
        headers=_deal["sender_headers"],
    )
    assert rev.status_code == 200

    # Recipient can no longer read.
    r_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/dealvault", headers=rec_hdr
    )
    assert r_list.status_code == 403


async def test_only_sender_can_revoke(client, _deal, session_maker):
    from sqlalchemy import select

    from app.models.deal import DealParticipant

    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec_hdr, _ = await _register(client, "r-rev2")
    await client.post(f"/api/deals/join/{token}", headers=rec_hdr)

    async with session_maker() as db:
        row = (
            await db.execute(
                select(DealParticipant).where(DealParticipant.invite_token == token)
            )
        ).scalar_one()
        recipient_uid = row.user_id

    r = await client.post(
        f"/api/deals/{_deal['deal_id']}/participants/{recipient_uid}/revoke",
        headers=_deal["carrier_headers"],
    )
    assert r.status_code == 403


async def test_list_participants_visible_to_deal_members(client, _deal):
    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec_hdr, _ = await _register(client, "r-list")
    await client.post(f"/api/deals/join/{token}", headers=rec_hdr)

    # Sender sees.
    s_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/participants",
        headers=_deal["sender_headers"],
    )
    assert s_list.status_code == 200
    assert len(s_list.json()) == 1
    assert s_list.json()[0]["role"] == "recipient"

    # Carrier sees.
    c_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/participants",
        headers=_deal["carrier_headers"],
    )
    assert c_list.status_code == 200
    assert len(c_list.json()) == 1

    # Third party — 403.
    other_hdr, _ = await _register(client, "r-out")
    o_list = await client.get(
        f"/api/deals/{_deal['deal_id']}/participants", headers=other_hdr
    )
    assert o_list.status_code == 403


async def test_decrypt_for_me_endpoint_returns_plaintext_for_recipient_of_e2e_message(
    client, _deal, session_maker
):
    """Full e2e roundtrip: sender publishes e2e-message with recipient's read_pkg.
    Recipient calls server-mediated decrypt endpoint → gets plaintext."""
    import base64
    import os as _os

    from app.core.threshold import nip04_encrypt
    from app.models.deal import DealVaultMessage
    from app.models.user import User
    from tests.conftest import SEED_PASSWORD

    inv = await client.post(
        f"/api/deals/{_deal['deal_id']}/invite-recipient",
        headers=_deal["sender_headers"],
    )
    token = inv.json()["invite_token"]
    rec_hdr, _ = await _register(client, "r-dec")
    await client.post(f"/api/deals/join/{token}", headers=rec_hdr)

    # Get sender's + recipient's + carrier's npubs.
    from sqlalchemy import select

    from app.models.deal import Deal, DealParticipant

    async with session_maker() as db:
        deal = await db.get(Deal, _deal["deal_id"])
        sender = await db.get(User, deal.sender_id)
        carrier = await db.get(User, deal.carrier_id)
        p_row = (
            await db.execute(
                select(DealParticipant).where(DealParticipant.invite_token == token)
            )
        ).scalar_one()
        recipient = await db.get(User, p_row.user_id)
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

    # Build minimal e2e_payload with plaintext "hello recipient".
    session_key = _os.urandom(32)
    fake_nonce = _os.urandom(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ciphertext = AESGCM(session_key).encrypt(fake_nonce, b"hello recipient", None)

    payload = {
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "nonce": base64.b64encode(fake_nonce).decode("ascii"),
        "wrapped_shares": {
            "sender": nip04_encrypt(b"\x01" + session_key, sender_nsec, sender_npub),
            "carrier": nip04_encrypt(b"\x02" + session_key, sender_nsec, carrier_npub),
            "arbiter": nip04_encrypt(b"\x03" + session_key, sender_nsec, sender_npub),  # no real arbiter — reuse sender npub for shape only
        },
        "read_packages": {
            "sender": nip04_encrypt(session_key, sender_nsec, sender_npub),
            "carrier": nip04_encrypt(session_key, sender_nsec, carrier_npub),
            f"recipient_{recipient_id}": nip04_encrypt(
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

    # Recipient asks server to decrypt for them.
    dec = await client.post(
        f"/api/deals/{_deal['deal_id']}/dealvault/messages/{msg_id}/decrypt-for-me",
        headers=rec_hdr,
    )
    assert dec.status_code == 200, dec.json()
    assert dec.json()["text"] == "hello recipient"
