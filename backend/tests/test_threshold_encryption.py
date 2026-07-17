"""T2.3 — threshold 2-of-3 e2e vault message + arbiter reveal."""
from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.core.threshold import nip04_encrypt


def _make_e2e_payload(
    sender_nsec: str,
    sender_npub: str,
    carrier_npub: str,
    arbiter_npub: str,
) -> dict:
    """Simulate what the browser client will produce.

    We stub SSS by using three distinct 33-byte "share" payloads; the real
    Shamir combine is verified via the frontend lib. Backend only stores and,
    on arbiter reveal, NIP-04 decrypts the arbiter's wrapped share — it doesn't
    interpret the plaintext bytes.
    """
    session_key = os.urandom(32)
    share_sender = b"\x01" + session_key
    share_carrier = b"\x02" + session_key
    share_arbiter = b"\x03" + session_key
    fake_ct = b"CIPHER-" + os.urandom(24)
    fake_nonce = os.urandom(12)
    return {
        "ciphertext": base64.b64encode(fake_ct).decode("ascii"),
        "nonce": base64.b64encode(fake_nonce).decode("ascii"),
        "wrapped_shares": {
            "sender": nip04_encrypt(share_sender, sender_nsec, sender_npub),
            "carrier": nip04_encrypt(share_carrier, sender_nsec, carrier_npub),
            "arbiter": nip04_encrypt(share_arbiter, sender_nsec, arbiter_npub),
        },
        "read_packages": {
            "sender": nip04_encrypt(session_key, sender_nsec, sender_npub),
            "carrier": nip04_encrypt(session_key, sender_nsec, carrier_npub),
        },
    }


@pytest.fixture
async def _e2e_deal(client, session_maker):
    """Fresh carrier + sender + matched deal, plus platform arbiter with
    ARBITER_USER_ID env pointing at them. Returns npubs for the three parties."""
    from tests.conftest import SEED_PASSWORD, unique_email

    # Sender
    s_email = unique_email("e2e-s")
    await client.post(
        "/api/auth/register",
        json={"email": s_email, "password": SEED_PASSWORD, "display_name": "E2eS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}
    s_status = await client.get("/api/me/keypair/status", headers=s_headers)
    sender_npub = s_status.json()["npub"]
    # Export sender nsec so test can NIP-04-encrypt on their behalf.
    s_exp = await client.post(
        "/api/me/keypair/export",
        headers=s_headers,
        json={"password": SEED_PASSWORD},
    )
    sender_nsec = s_exp.json()["nsec_hex"]

    # Carrier
    c_email = unique_email("e2e-c")
    await client.post(
        "/api/auth/register",
        json={
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "E2eC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    c_status = await client.get("/api/me/keypair/status", headers=c_headers)
    carrier_npub = c_status.json()["npub"]

    # Arbiter — role=arbiter user. Bootstrap via direct DB row + env pointer.
    from sqlalchemy import update

    from app.core.keypair import encrypt_nsec, generate_keypair
    from app.models.user import User
    from app.core.security import hash_password

    arb_nsec, arb_npub = generate_keypair()
    arb_nonce, arb_ct = encrypt_nsec(arb_nsec)
    async with session_maker() as db:
        arbiter = User(
            email=unique_email("arb"),
            password_hash=hash_password(SEED_PASSWORD),
            display_name="Arb",
            role="arbiter",
            nostr_pubkey=arb_npub,
            nsec_encrypted=arb_ct,
            nsec_nonce=arb_nonce,
            key_self_custody=False,
        )
        db.add(arbiter)
        await db.commit()
        await db.refresh(arbiter)
        arbiter_id = arbiter.id

    os.environ["ARBITER_USER_ID"] = str(arbiter_id)

    # Trip + match.
    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "TE2",
            "destination": "END",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]
    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000004444",
                "origin": "TE2",
                "destination": "END",
                "category": "document",
                "declared_value": 40.0,
            },
        },
    )
    deal_id = match.json()["id"]

    # Arbiter login for later use.
    a_login = await client.post(
        "/api/auth/login",
        json={"login": arbiter.email, "password": SEED_PASSWORD},
    )
    a_headers = {"Authorization": f"Bearer {a_login.json()['access_token']}"}

    yield {
        "sender_headers": s_headers,
        "carrier_headers": c_headers,
        "arbiter_headers": a_headers,
        "sender_nsec": sender_nsec,
        "sender_npub": sender_npub,
        "carrier_npub": carrier_npub,
        "arbiter_npub": arb_npub,
        "arbiter_nsec": arb_nsec,
        "deal_id": deal_id,
    }

    os.environ.pop("ARBITER_USER_ID", None)


async def test_arbiter_info_reports_platform_pubkey(client, _e2e_deal):
    d = _e2e_deal
    resp = await client.get("/api/threshold/arbiter-info", headers=d["sender_headers"])
    assert resp.status_code == 200
    assert resp.json()["npub"] == d["arbiter_npub"]


async def test_arbiter_info_503_when_env_missing(client, _e2e_deal):
    d = _e2e_deal
    os.environ.pop("ARBITER_USER_ID", None)
    resp = await client.get("/api/threshold/arbiter-info", headers=d["sender_headers"])
    assert resp.status_code == 503


async def test_e2e_write_stores_blob_and_hides_text(client, _e2e_deal, session_maker):
    from sqlalchemy import select

    from app.models.deal import DealVaultMessage

    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["is_e2e"] is True
    assert body["text"] is None
    assert body["ciphertext_b64"] == payload["ciphertext"]
    assert body["nonce_b64"] == payload["nonce"]
    assert body["read_packages"]["sender"] == payload["read_packages"]["sender"]
    assert body["read_packages"]["carrier"] == payload["read_packages"]["carrier"]

    # DB check: server has ciphertext bytes, wrapped_shares JSON, no plaintext.
    async with session_maker() as db:
        result = await db.execute(
            select(DealVaultMessage).where(DealVaultMessage.id == body["id"])
        )
        msg = result.scalar_one()
        assert msg.is_e2e is True
        assert msg.wrapped_shares.keys() == {"sender", "carrier", "arbiter"}
        assert msg.text is None  # property returns None for e2e


async def test_e2e_and_text_are_mutually_exclusive(client, _e2e_deal):
    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload, "text": "also plaintext"},
    )
    assert resp.status_code == 422
    assert "mutually exclusive" in resp.json()["detail"].lower()


async def test_e2e_payload_shape_validated(client, _e2e_deal):
    d = _e2e_deal
    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": {"ciphertext": "x", "nonce": "y"}},  # missing shares
    )
    assert resp.status_code == 422


async def test_reveal_my_share_returns_envelope(client, _e2e_deal):
    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    write = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload},
    )
    msg_id = write.json()["id"]

    # Sender reveals sender share.
    r = await client.post(
        f"/api/threshold/dealvault/messages/{msg_id}/reveal-my-share",
        headers=d["sender_headers"],
    )
    assert r.status_code == 200
    assert r.json()["role"] == "sender"
    assert r.json()["envelope"] == payload["wrapped_shares"]["sender"]

    # Carrier reveals carrier share.
    r2 = await client.post(
        f"/api/threshold/dealvault/messages/{msg_id}/reveal-my-share",
        headers=d["carrier_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["role"] == "carrier"
    assert r2.json()["envelope"] == payload["wrapped_shares"]["carrier"]


async def test_reveal_my_share_forbidden_for_third_party(client, _e2e_deal):
    """A user not in the deal cannot fetch its shares."""
    from tests.conftest import SEED_PASSWORD, unique_email

    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    write = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload},
    )
    msg_id = write.json()["id"]

    outsider_email = unique_email("outs")
    await client.post(
        "/api/auth/register",
        json={
            "email": outsider_email,
            "password": SEED_PASSWORD,
            "display_name": "Out",
        },
    )
    login = await client.post(
        "/api/auth/login",
        json={"login": outsider_email, "password": SEED_PASSWORD},
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.post(
        f"/api/threshold/dealvault/messages/{msg_id}/reveal-my-share",
        headers=hdr,
    )
    assert r.status_code == 403


async def test_arbiter_reveal_returns_unwrapped_shares_with_audit(
    client, _e2e_deal, session_maker
):
    from sqlalchemy import select

    from app.models.deal import DealEvent, DealEventType

    d = _e2e_deal

    # Write two e2e messages.
    payloads = []
    for _ in range(2):
        p = _make_e2e_payload(
            d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"]
        )
        r = await client.post(
            f"/api/deals/{d['deal_id']}/dealvault/messages",
            headers=d["sender_headers"],
            json={"e2e_payload": p},
        )
        assert r.status_code == 201, r.json()
        payloads.append(p)

    # Open a dispute (participant-initiated) so arbiter-reveal precondition is met.
    disp = await client.post(
        f"/api/deals/{d['deal_id']}/dispute",
        headers=d["sender_headers"],
        json={"reason": "test"},
    )
    assert disp.status_code == 201, disp.json()

    reveal = await client.post(
        f"/api/threshold/disputes/{d['deal_id']}/arbiter-reveal",
        headers=d["arbiter_headers"],
    )
    assert reveal.status_code == 200, reveal.json()
    body = reveal.json()
    assert len(body["revealed"]) == 2
    for entry in body["revealed"]:
        # Unwrapped share is 33 bytes (our fake role-tag + 32-byte "session_key").
        share = base64.b64decode(entry["arbiter_share_b64"])
        assert len(share) == 33
        assert share[0] == 3  # arbiter role tag from _make_e2e_payload

    # Audit event recorded (arbiter_opened with kind=arbiter_share_revealed).
    async with session_maker() as db:
        rows = await db.execute(
            select(DealEvent).where(
                DealEvent.deal_id == d["deal_id"],
                DealEvent.event_type == DealEventType.arbiter_opened,
            )
        )
        arbiter_events = list(rows.scalars())
        assert any(
            (e.payload or {}).get("kind") == "arbiter_share_revealed"
            for e in arbiter_events
        )


async def test_arbiter_reveal_requires_arbiter_role(client, _e2e_deal):
    d = _e2e_deal
    resp = await client.post(
        f"/api/threshold/disputes/{d['deal_id']}/arbiter-reveal",
        headers=d["sender_headers"],
    )
    assert resp.status_code == 403


async def test_nip04_roundtrip_correctness():
    """Sanity: NIP-04 encrypt→decrypt is symmetric on our helpers."""
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip04_decrypt, nip04_encrypt

    a_nsec, a_npub = generate_keypair()
    b_nsec, b_npub = generate_keypair()
    payload = b"session-key-abc-123-XYZ"
    ct = nip04_encrypt(payload, a_nsec, b_npub)
    assert nip04_decrypt(ct, b_nsec, a_npub) == payload
