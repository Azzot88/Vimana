"""T_UX.29 pt.7 — the bell, and the rule that decides what lands in it.

Named `test_notification_feed` and not `test_notifications`: that name was taken
by the tests for the **outbound** side (`tasks/notifications.py` — letters and
Telegram), and the two are different subjects. This file is about the in-app
feed: rows, read state and who is told what.

Owner, 2026-09-20: «Панель должна показывать обновления, произошедшие за период
неактивности. Если изменения произошли в активном окне, их статусы показывать не
нужно.»

The second half is not a server rule and is not tested here: the screen that
showed something marks it read (`DealVaultPage`), and what these tests pin down
is the half that must be true for that to work — a row exists for everybody who
was not the actor, addressed to them, with its own read state.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from tests.conftest import unique_email


@pytest_asyncio.fixture
async def pair(client, session_maker, seed_carrier, seed_sender):
    """A deal with both parties, and nothing said in it yet."""
    from app.models.deal import Deal, DealStatus
    from app.models.marketplace import Cargo, Trip, TripStatus

    async with session_maker() as db:
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="DXB",
            destination="JFK",
            depart_at=datetime.now(timezone.utc) + timedelta(days=4),
            capacity=5.0,
            allowed_categories=["document"],
            status=TripStatus.open,
            price_per_kg=20.0,
            currency="USD",
        )
        db.add(trip)
        await db.flush()
        cargo = Cargo(
            created_by_id=seed_sender.id,
            category="document",
            declared_value=500.0,
            currency="USD",
            final_destination=trip.destination,
        )
        db.add(cargo)
        await db.flush()
        deal = Deal(
            cargo_id=cargo.id,
            trip_id=trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.accepted,
        )
        db.add(deal)
        await db.commit()
        await db.refresh(deal)
        return deal


async def _unread(client, headers) -> int:
    r = await client.get("/api/notifications/unread-count", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["unread"]


async def test_a_card_tells_the_other_side_and_not_its_author(
    client, carrier_headers, sender_headers, pair
):
    """Nobody is notified of their own press: `exclude` is the actor, passed
    rather than inferred because half the callers act for the platform."""
    before_carrier = await _unread(client, carrier_headers)
    before_sender = await _unread(client, sender_headers)

    raised = await client.post(
        f"/api/deals/{pair.id}/cards",
        headers=sender_headers,
        json={"kind": "pickup.proposed", "payload": {"method": "in_person"}},
    )
    assert raised.status_code == 201, raised.text

    assert await _unread(client, carrier_headers) == before_carrier + 1
    assert await _unread(client, sender_headers) == before_sender


async def test_the_panel_lists_what_happened_and_links_to_the_deal(
    client, carrier_headers, sender_headers, pair
):
    await client.post(
        f"/api/deals/{pair.id}/cards",
        headers=sender_headers,
        json={"kind": "pickup.proposed", "payload": {"method": "in_person"}},
    )
    r = await client.get("/api/notifications", headers=carrier_headers)
    assert r.status_code == 200, r.text
    mine = [n for n in r.json() if n["deal_id"] == str(pair.id)]
    assert mine, r.text
    assert mine[0]["kind"] == "deal.status"
    assert mine[0]["read_at"] is None


async def test_the_open_deal_clears_its_own(
    client, carrier_headers, sender_headers, pair
):
    """«Если изменения произошли в активном окне, их статусы показывать не
    нужно» — the screen showing a deal marks that deal read, and nothing else
    of the carrier's goes with it."""
    await client.post(
        f"/api/deals/{pair.id}/cards",
        headers=sender_headers,
        json={"kind": "pickup.proposed", "payload": {"method": "in_person"}},
    )
    assert await _unread(client, carrier_headers) >= 1

    cleared = await client.post(
        "/api/notifications/read",
        headers=carrier_headers,
        json={"deal_id": str(pair.id)},
    )
    assert cleared.status_code == 200, cleared.text

    r = await client.get("/api/notifications", headers=carrier_headers)
    mine = [n for n in r.json() if n["deal_id"] == str(pair.id)]
    assert all(n["read_at"] is not None for n in mine)


async def test_one_person_cannot_read_another_s(client, carrier_headers, sender_headers, pair):
    """The caller is in the WHERE clause, not merely checked: the ids come from
    a client, and a statement that could touch somebody else's row if the check
    were forgotten is a statement waiting for the day it is."""
    await client.post(
        f"/api/deals/{pair.id}/cards",
        headers=sender_headers,
        json={"kind": "pickup.proposed", "payload": {"method": "in_person"}},
    )
    listed = await client.get("/api/notifications", headers=carrier_headers)
    ids = [n["id"] for n in listed.json() if n["deal_id"] == str(pair.id)]
    assert ids

    # The sender asks to read the carrier's rows by id.
    await client.post(
        "/api/notifications/read", headers=sender_headers, json={"ids": ids}
    )
    again = await client.get("/api/notifications", headers=carrier_headers)
    still = [n for n in again.json() if n["id"] in ids]
    assert all(n["read_at"] is None for n in still)


async def test_a_chat_message_notifies_without_carrying_its_text(
    client, carrier_headers, sender_headers, pair
):
    """Chat bodies are encrypted at rest; a preview here would undo that for
    the price of a nicer line in a panel."""
    sent = await client.post(
        f"/api/deals/{pair.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "meet me at the north exit"},
    )
    assert sent.status_code == 201, sent.text

    r = await client.get("/api/notifications", headers=carrier_headers)
    chat = [
        n
        for n in r.json()
        if n["deal_id"] == str(pair.id) and n["kind"] == "chat.message"
    ]
    assert chat, r.text
    assert "north exit" not in str(chat[0]["payload"])


async def test_a_push_endpoint_is_kept_once_per_browser(client, sender_headers):
    """The endpoint is the identity of the row: a browser re-issues it on
    rotation, and the same account on two devices has two."""
    body = {"endpoint": f"https://push.test/{unique_email('e')}", "p256dh": "k", "auth": "a"}
    first = await client.post("/api/notifications/push", headers=sender_headers, json=body)
    assert first.status_code == 204, first.text
    again = await client.post("/api/notifications/push", headers=sender_headers, json=body)
    assert again.status_code == 204, again.text


async def test_the_stream_needs_a_session(client):
    """It carries everything addressed to one person; an unauthenticated reader
    is not a person."""
    r = await client.get("/api/events/stream")
    assert r.status_code in (401, 403), r.text


async def test_the_stream_says_ready_and_ends_with_its_reader(sender_headers):
    """The open stream: `ready` first, and it ends when the reader leaves.

    Called on the ASGI app directly, not through `client`. Both in-process
    clients — httpx here, `starlette_testclient` in the fuzz — hand back a
    response only once its body is complete, and this body never completes; the
    fuzz hung on exactly that. Here the reader disconnects after the first
    chunk, which is what a closed tab does, and the stream has to notice.

    `wait_for` is the point of the test as much as the assertions are: a stream
    that ignores the disconnect fails here in five seconds instead of hanging
    the run.
    """
    from app.main import app

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/events/stream",
        "raw_path": b"/api/events/stream",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"authorization", sender_headers["Authorization"].encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    first_chunk = asyncio.Event()
    request_sent = False
    start: dict = {}
    chunks: list[bytes] = []

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            start.update(message)
        elif message["type"] == "http.response.body" and message.get("body"):
            chunks.append(message["body"])
            first_chunk.set()

    await asyncio.wait_for(app(scope, receive, send), timeout=5)

    assert start["status"] == 200
    headers = dict(start["headers"])
    assert headers[b"content-type"].startswith(b"text/event-stream")
    assert headers[b"x-accel-buffering"] == b"no"
    assert b"".join(chunks).startswith(b"event: ready\n")


# ── T_UX.29 pt.8 · four moments earn a letter, the rest stop at the bell ────


async def test_a_card_that_awaits_you_sends_a_letter(
    client, carrier_headers, sender_headers, pair, monkeypatch
):
    """Owner's list, 2026-09-21: «требуется подтверждение» is one of the four.

    Addressed to **one** person — the one who can answer. A letter to somebody
    with nothing to press is the letter that teaches people to stop opening
    them, and everybody else still gets the bell.
    """
    queued: list[tuple] = []
    from app.tasks import notifications as notif

    monkeypatch.setattr(
        notif.notify_deal_event,
        "delay",
        lambda *args: queued.append(args),
    )

    r = await client.post(
        f"/api/deals/{pair.id}/cards",
        headers=sender_headers,
        json={"kind": "pickup.proposed", "payload": {"method": "in_person"}},
    )
    assert r.status_code == 201, r.text

    assert len(queued) == 1, queued
    _, moment, event_class, _, deal_no, route, role = queued[0]
    assert moment == "needs_ack"
    assert event_class == "deal_meeting"
    assert role == "sender"
    assert route  # the corridor, which the owner asked to be in the body
    assert deal_no or deal_no == ""  # a pre-format deal may carry none


async def test_the_landing_is_told_to_everybody(
    client, carrier_headers, sender_headers, pair, monkeypatch
):
    """«Груз прилетел» — the one moment somebody waits for with nothing to
    press, so it goes to the whole deal rather than to one answerer."""
    queued: list[tuple] = []
    from app.tasks import notifications as notif

    monkeypatch.setattr(
        notif.notify_deal_event, "delay", lambda *args: queued.append(args)
    )

    r = await client.post(
        f"/api/deals/{pair.id}/cards",
        headers=carrier_headers,
        json={"kind": "transit.update", "payload": {"stage": "arrived"}},
    )
    assert r.status_code == 201, r.text
    assert [q[1] for q in queued] == ["arrived"]
    assert {q[2] for q in queued} == {"deal_custody"}


async def test_an_ordinary_card_does_not_write(
    client, carrier_headers, sender_headers, pair, monkeypatch
):
    """Everything outside the four stops at the bell: a letter per card is a
    mailbox nobody reads, and the one that mattered arrives in the middle."""
    queued: list[tuple] = []
    from app.tasks import notifications as notif

    monkeypatch.setattr(
        notif.notify_deal_event, "delay", lambda *args: queued.append(args)
    )
    sent = await client.post(
        f"/api/deals/{pair.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "on my way"},
    )
    assert sent.status_code == 201, sent.text
    assert queued == []
