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
            "payment_model": "cash_on_delivery",
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


async def test_inquiry_linked_to_deal_after_match(client, carrier_headers):
    """Before the match the chat names no deal; after it, that one.

    T3.11.23 — on a **fresh** sender. `deal_id` used to mean «the deal of this
    thread», and a thread was per trip, so it was empty until this test filled
    it. It now means «the deal to carry on in» and a chat is per person, so
    between the two shared seed accounts there is almost always one running from
    an earlier test — and «before» stopped being empty for a reason that has
    nothing to do with matching.

    Written with its own sender so both halves are statements again.
    """
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    email = unique_email("linked")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Linked"}
    )
    sender_headers = {"Authorization": f"Bearer {await _login(client, email)}"}

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


async def test_messages_from_both_trips_are_in_one_thread(client, carrier_headers):
    """A conversation is a conversation. Two questions about two trips are two
    messages in the same place, which is what a person would expect and what the
    old model could not express.

    On a **fresh** sender, not the shared seed one. The fold gave that pair every
    message they had ever exchanged in any thread, and the listing is ascending —
    so two new messages land past the first page and the test fails for a reason
    that has nothing to do with what it checks. Third time this suite has taught
    the same lesson (`ENVIRONMENT §8`): a shared fixture accumulates, and an
    assertion about «what is in the thread» needs a thread with a known floor.
    """
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    email = unique_email("chatfold")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Fold"}
    )
    sender_headers = {"Authorization": f"Bearer {await _login(client, email)}"}

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

    # Read off the row rather than through the API: what the card shows is
    # covered by `test_the_deal_card_carries_number_name_and_price`, and what is
    # checked here is that the column itself is filled at match time.
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


async def test_asks_counts_people_not_messages(client, carrier_headers):
    """«Сколько человек спросили про этот рейс», answered off the message.

    The panel counted threads while a thread was per `(trip, sender)`. With one
    chat per person there is nothing per-trip left to count, so the trip moved
    onto the message that raises it — and the count is over **distinct chats**:
    somebody who writes four times about one trip has asked once, and counting
    messages would turn a talkative sender into a queue of four.
    """
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    trip_id = await _make_open_trip(client, carrier_headers)

    async def _ask(times: int) -> None:
        email = unique_email("asker")
        await make_account(
            {"email": email, "password": SEED_PASSWORD, "display_name": "Asker"}
        )
        headers = {"Authorization": f"Bearer {await _login(client, email)}"}
        chat = (
            await client.post(f"/api/trips/{trip_id}/inquiry", headers=headers)
        ).json()["id"]
        for i in range(times):
            r = await client.post(
                f"/api/inquiries/{chat}/messages",
                headers=headers,
                json={"text": f"вопрос {i}", "about_trip_id": trip_id},
            )
            assert r.status_code == 201, r.text

    await _ask(4)
    await _ask(1)

    counts = await client.get("/api/trips/ask-counts", headers=carrier_headers)
    assert counts.status_code == 200, counts.text
    assert counts.json().get(trip_id) == 2


async def test_asks_are_only_about_my_own_trips(
    client, carrier_headers, sender_headers
):
    """The number is a fact about the carrier's own listing. On somebody else's
    it is a demand figure they never published."""
    trip_id = await _make_open_trip(client, carrier_headers)
    chat = (
        await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    ).json()["id"]
    await client.post(
        f"/api/inquiries/{chat}/messages",
        headers=sender_headers,
        json={"text": "спрашиваю", "about_trip_id": trip_id},
    )

    mine = await client.get("/api/trips/ask-counts", headers=carrier_headers)
    theirs = await client.get("/api/trips/ask-counts", headers=sender_headers)
    assert trip_id in mine.json()
    assert trip_id not in theirs.json()


async def test_the_deal_card_carries_number_name_and_price(
    client, sender_headers, carrier_headers
):
    """T3.11.23 — a deal in a list has to be identifiable without opening it.

    The card is three things: the number people dictate, a name **derived** from
    what is being carried and where (the client joins category and route — a
    name field would come back empty), and the agreed price. The price appears
    only once both sides have agreed: a deal under negotiation has none, and a
    zero would be a claim neither side made.
    """
    from tests.conftest import agree_terms

    trip_id = await _make_open_trip(client, carrier_headers)
    deal_id = (
        await client.post(
            "/api/deals/match",
            headers=sender_headers,
            json={
                "trip_id": trip_id,
                "order": {
                    "recipient_contact": "+10000000001",
                    "origin": "INQ",
                    "destination": "TST",
                    "category": "document",
                    "declared_value": 100.0,
                },
            },
        )
    ).json()["id"]

    def _find(items):
        return next(d for d in items if d["id"] == deal_id)

    before = await client.get("/api/deals", headers=sender_headers)
    assert before.status_code == 200, before.text
    card = _find(before.json()["items"])
    assert card["shipment_no"] and len(card["shipment_no"]) == 8
    assert card["chat_id"]
    assert card["cargo_category"] == "document"
    assert (card["origin"], card["destination"]) == ("INQ", "TST")
    # Nothing agreed yet — and that is printed as nothing, not as zero.
    assert card["price_total"] is None

    await agree_terms(
        client, sender_headers, carrier_headers, deal_id, price_total=140
    )
    after = await client.get("/api/deals", headers=sender_headers)
    card = _find(after.json()["items"])
    assert card["price_total"] == 140
    assert card["currency"] == "USD"


async def test_deals_can_be_narrowed_to_one_chat(
    client, sender_headers, carrier_headers
):
    """T3.11.23 — the chat screen lists the deals nested in *this* chat.

    Filtering is stacked on top of the ownership filter, never instead of it: a
    chat id is not a capability, and a guessed one must not read anybody's deals
    but the caller's own.
    """
    trip_id = await _make_open_trip(client, carrier_headers)
    order = {
        "recipient_contact": "+10000000002",
        "origin": "INQ",
        "destination": "TST",
        "category": "document",
        "declared_value": 10.0,
    }
    deal_id = (
        await client.post(
            "/api/deals/match",
            headers=sender_headers,
            json={"trip_id": trip_id, "order": order},
        )
    ).json()["id"]
    chat_id = (
        await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    ).json()["id"]

    mine = await client.get(
        "/api/deals", headers=sender_headers, params={"chat_id": chat_id}
    )
    assert mine.status_code == 200, mine.text
    assert deal_id in [d["id"] for d in mine.json()["items"]]
    assert all(d["chat_id"] == chat_id for d in mine.json()["items"])

    # The carrier's own page filtered by the same chat sees the same deal —
    # they are the other participant.
    theirs = await client.get(
        "/api/deals", headers=carrier_headers, params={"chat_id": chat_id}
    )
    assert deal_id in [d["id"] for d in theirs.json()["items"]]

    # A stranger holding the same id sees nothing: the ownership filter runs
    # first, and the chat id only narrows what is already the caller's.
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    email = unique_email("chatfilter")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Stranger"}
    )
    stranger = {"Authorization": f"Bearer {await _login(client, email)}"}
    seen = await client.get(
        "/api/deals", headers=stranger, params={"chat_id": chat_id}
    )
    assert seen.status_code == 200, seen.text
    assert seen.json()["items"] == []


async def test_chat_list_names_the_person_and_counts_deals(
    client, sender_headers, carrier_headers
):
    """T3.11.23 — a list of chats is a list of people.

    `counterparty_name` is what makes the row openable; `deal_count` is what the
    screen asks before offering a choice of deal, since the owner wanted the
    picker «только если появляется вторая сделка».
    """
    trip_id = await _make_open_trip(client, carrier_headers)
    chat_id = (
        await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    ).json()["id"]
    await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000003",
                "origin": "INQ",
                "destination": "TST",
                "category": "document",
                "declared_value": 10.0,
            },
        },
    )

    chats = await client.get("/api/inquiries", headers=sender_headers)
    assert chats.status_code == 200, chats.text
    row = next(c for c in chats.json() if c["id"] == chat_id)
    assert row["counterparty_name"]
    assert row["carrier_id"] != row["sender_id"]
    assert row["deal_count"] >= 1
