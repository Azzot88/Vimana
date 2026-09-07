"""T1.22 — pre-deal inquiry chat between sender and carrier."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text
from tests.conftest import make_account


async def _make_open_trip(client, carrier_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "legs": [
                {
                    "origin": "INQ",
                    "destination": "TST",
                    "depart_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
                }
            ],
            "capacity": 3.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_open_inquiry_creates_thread(client, carrier_headers, sender_headers):
    """T3.11.23 — the response names the chat and echoes the trip asked about.

    It used to assert `deal_id is None` on the theory that a fresh thread has no
    deal. That stopped being a property of *opening* one: a chat belongs to the
    pair and outlives every deal in it, so between two shared seed accounts it
    is normal to find one running. The field now means «the deal to carry on
    in», and the test that owns it is the one below.
    """
    trip_id = await _make_open_trip(client, carrier_headers)
    resp = await client.post(
        f"/api/trips/{trip_id}/inquiry", headers=sender_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["trip_id"] == trip_id
    assert body["id"]


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
                "SELECT text_ciphertext, text_nonce FROM chat_messages "
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
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "O"},
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


# ── T3.11.23 · one chat per person ─────────────────────────────────────────


async def test_two_trips_with_one_carrier_share_a_chat(
    client, sender_headers, carrier_headers
):
    """The whole revision, in one assertion.

    `trip_inquiries` was keyed `(trip_id, sender_id)`: writing to one carrier
    about three trips produced three threads with the same person, and none of
    them was «our conversation». A chat is keyed by the pair.
    """
    first = await _make_open_trip(client, carrier_headers)
    second = await _make_open_trip(client, carrier_headers)

    a = await client.post(f"/api/trips/{first}/inquiry", headers=sender_headers)
    b = await client.post(f"/api/trips/{second}/inquiry", headers=sender_headers)
    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text
    assert a.json()["id"] == b.json()["id"]

    # The trip is echoed from the request, not owned by the thread — which is
    # what «рейс становится содержимым» means in the response shape.
    assert a.json()["trip_id"] == first
    assert b.json()["trip_id"] == second


async def test_a_chat_is_the_same_from_both_sides(
    client, sender_headers, carrier_headers
):
    """`(A, B)` and `(B, A)` are one row. The pair is stored ordered and the
    unique index makes «one per person» a fact of the database rather than a
    habit of the code."""
    trip = await _make_open_trip(client, carrier_headers)
    opened = await client.post(f"/api/trips/{trip}/inquiry", headers=sender_headers)
    chat_id = opened.json()["id"]

    for headers in (sender_headers, carrier_headers):
        listing = await client.get("/api/inquiries", headers=headers)
        assert listing.status_code == 200, listing.text
        assert chat_id in {c["id"] for c in listing.json()}


async def test_messages_from_both_trips_are_in_one_thread(
    client, sender_headers, carrier_headers
):
    """A conversation is a conversation. Two questions about two trips are two
    messages in the same place, which is what a person would expect and what the
    old model could not express."""
    first = await _make_open_trip(client, carrier_headers)
    second = await _make_open_trip(client, carrier_headers)
    chat_id = (
        await client.post(f"/api/trips/{first}/inquiry", headers=sender_headers)
    ).json()["id"]
    await client.post(f"/api/trips/{second}/inquiry", headers=sender_headers)

    for text_ in ("про первый рейс", "и про второй"):
        r = await client.post(
            f"/api/inquiries/{chat_id}/messages",
            headers=sender_headers,
            json={"text": text_},
        )
        assert r.status_code == 201, r.text

    got = await client.get(
        f"/api/inquiries/{chat_id}/messages",
        headers=carrier_headers,
        params={"limit": 100},
    )
    assert got.status_code == 200, got.text
    texts = [m["text"] for m in got.json()["items"]]
    assert "про первый рейс" in texts
    assert "и про второй" in texts


async def test_the_chat_names_the_deal_to_carry_on_in(
    client, sender_headers, carrier_headers
):
    """Several deals can share a chat, so `deal_id` is «the one they are in the
    middle of», newest first — not «the deal of this thread», which is a
    sentence the old per-trip model could say and this one cannot."""
    trip_id = await _make_open_trip(client, carrier_headers)
    matched = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000000",
                "origin": "DXB",
                "destination": "JFK",
                "category": "document",
                "declared_value": 100.0,
                "description": "chat nesting probe",
            },
        },
    )
    assert matched.status_code == 201, matched.text
    deal_id = matched.json()["id"]

    opened = await client.post(
        f"/api/trips/{trip_id}/inquiry", headers=sender_headers
    )
    assert opened.json()["deal_id"] == deal_id


async def test_a_matched_deal_gets_a_chat_and_a_spoken_number(
    client, sender_headers, carrier_headers, session_maker
):
    """«Кнопка с доски открывает сделку, но также сначала открывает чат, а уже
    внутри него сделку.» The chat is the container and exists before the deal it
    holds; the number is what a person dictates instead of a UUID."""
    trip_id = await _make_open_trip(client, carrier_headers)
    matched = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000000",
                "origin": "DXB",
                "destination": "JFK",
                "category": "document",
                "declared_value": 100.0,
                "description": "shipment number probe",
            },
        },
    )
    assert matched.status_code == 201, matched.text
    chat = (
        await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    ).json()
    assert chat["deal_id"] == matched.json()["id"]

    import uuid as uuidlib

    from sqlalchemy import select

    from app.models.deal import Deal

    # Read off the row: the number is not on `DealOut` yet — the card that shows
    # it is this task's frontend half.
    async with session_maker() as db:
        deal = (
            await db.execute(
                select(Deal).where(Deal.id == uuidlib.UUID(matched.json()["id"]))
            )
        ).scalar_one()
        assert deal.chat_id is not None
        assert deal.shipment_no and len(deal.shipment_no) == 8
        # Dictated aloud, so the characters that get misheard are not in it.
        assert not set(deal.shipment_no) & set("01OIL")
