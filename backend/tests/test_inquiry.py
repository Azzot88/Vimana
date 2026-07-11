"""T1.22 — pre-deal inquiry chat between sender and carrier."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text


async def _make_open_trip(client, carrier_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "INQ",
            "destination": "TST",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
            "capacity": 3.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_open_inquiry_creates_thread(client, carrier_headers, sender_headers):
    trip_id = await _make_open_trip(client, carrier_headers)
    resp = await client.post(
        f"/api/trips/{trip_id}/inquiry", headers=sender_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["trip_id"] == trip_id
    assert body["deal_id"] is None


async def test_open_inquiry_is_idempotent(client, carrier_headers, sender_headers):
    trip_id = await _make_open_trip(client, carrier_headers)
    first = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    second = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    assert first.json()["id"] == second.json()["id"]


async def test_open_inquiry_on_own_trip_forbidden(client, carrier_headers):
    trip_id = await _make_open_trip(client, carrier_headers)
    resp = await client.post(f"/api/trips/{trip_id}/inquiry", headers=carrier_headers)
    assert resp.status_code == 400


async def test_post_and_read_encrypted_message(
    client, carrier_headers, sender_headers, session_maker
):
    trip_id = await _make_open_trip(client, carrier_headers)
    inq = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    inquiry_id = inq.json()["id"]

    plaintext = "Здравствуйте! Готовы принять посылку 2 кг?"
    post = await client.post(
        f"/api/inquiries/{inquiry_id}/messages",
        headers=sender_headers,
        json={"text": plaintext},
    )
    assert post.status_code == 201
    assert post.json()["text"] == plaintext

    # Direct SQL — bytes, no plaintext
    async with session_maker() as db:
        row = await db.execute(
            sa_text(
                "SELECT text_ciphertext, text_nonce FROM inquiry_messages "
                "WHERE id = :id"
            ),
            {"id": post.json()["id"]},
        )
        ct, nonce = row.one()
        assert ct is not None and nonce is not None
        assert plaintext.encode("utf-8") not in bytes(ct)

    # Carrier reads via API — plaintext returned
    got = await client.get(
        f"/api/inquiries/{inquiry_id}/messages", headers=carrier_headers
    )
    assert got.status_code == 200
    texts = [m["text"] for m in got.json()["items"] if m["text"]]
    assert plaintext in texts


async def test_outsider_cannot_read_inquiry(
    client, carrier_headers, sender_headers
):
    trip_id = await _make_open_trip(client, carrier_headers)
    inq = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    inquiry_id = inq.json()["id"]

    from tests.conftest import SEED_PASSWORD, _login, unique_email
    email = unique_email("outsider")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "O"},
    )
    token = await _login(client, email)
    outsider = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"/api/inquiries/{inquiry_id}/messages", headers=outsider
    )
    assert resp.status_code == 403


async def test_post_empty_message_rejected(
    client, carrier_headers, sender_headers
):
    trip_id = await _make_open_trip(client, carrier_headers)
    inq = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    inquiry_id = inq.json()["id"]
    resp = await client.post(
        f"/api/inquiries/{inquiry_id}/messages",
        headers=sender_headers,
        json={"text": "   "},
    )
    assert resp.status_code == 422


async def test_inquiry_linked_to_deal_after_match(
    client, carrier_headers, sender_headers
):
    trip_id = await _make_open_trip(client, carrier_headers)
    inq = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    inquiry_id = inq.json()["id"]
    assert inq.json()["deal_id"] is None

    match = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000020",
                "origin": "INQ",
                "destination": "TST",
                "category": "document",
                "declared_value": 100.0,
            },
        },
    )
    assert match.status_code == 201
    deal_id = match.json()["id"]

    # Refetch inquiry — expect deal_id linked
    inquiries = await client.get("/api/inquiries", headers=sender_headers)
    assert inquiries.status_code == 200
    thread = next(i for i in inquiries.json() if i["id"] == inquiry_id)
    assert thread["deal_id"] == deal_id


async def test_carrier_sees_inquiries_addressed_to_them(
    client, carrier_headers, sender_headers
):
    trip_id = await _make_open_trip(client, carrier_headers)
    inq = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    resp = await client.get("/api/inquiries", headers=carrier_headers)
    assert resp.status_code == 200
    assert any(i["id"] == inq.json()["id"] for i in resp.json())
