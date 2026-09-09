"""T3.11.19 — the sender's side: a request, and a subscription to a corridor.

366 posts in the market dump are «кто летит в ближайшие дни ЛА — Москва?». At a
five-day median horizon that is the rational move rather than a failure to use
the board: at the moment the sender looks, the trip they need does not exist yet.

What is worth asserting is the three decisions that make it a subscription and
not a classified ad: the window binds, «не пишите мне» is a different answer from
«закрыл», and the public view counts without naming.
"""
from __future__ import annotations

import uuid as uuidlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete

from app.models.marketplace import SenderRequest


def _window(start: int = 0, end: int = 10) -> dict:
    today = date.today()
    return {
        "window_from": (today + timedelta(days=start)).isoformat(),
        "window_to": (today + timedelta(days=end)).isoformat(),
    }


async def _file(client, headers, **over):
    body = {"origin": "LAX", "destination": "SVO", **_window(), **over}
    return await client.post("/api/requests", headers=headers, json=body)


async def test_a_request_is_filed_without_inventing_a_deal(client, sender_headers):
    """Deliberately not an `Order`: declared value, recipient and category are
    decisions this person has not made, and a form demanding them would be a
    form nobody fills in."""
    r = await _file(client, sender_headers, what="Документы, немного")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_open"] is True
    assert body["notify"] is True
    assert body["what"] == "Документы, немного"


async def test_a_backwards_window_is_refused(client, sender_headers):
    r = await _file(client, sender_headers, **_window(10, 2))
    assert r.status_code == 422, r.text


async def test_a_corridor_to_itself_is_refused(client, sender_headers):
    r = await _file(client, sender_headers, destination="LAX")
    assert r.status_code == 422, r.text


async def test_silencing_is_not_the_same_as_closing(client, sender_headers):
    """«Я спрашиваю, не пишите мне» leaves a public statement that somebody
    wants this corridor, and carriers read it. Collapsing the two switches would
    delete that statement to stop a letter."""
    filed = await _file(client, sender_headers)
    request_id = filed.json()["id"]

    quiet = await client.patch(
        f"/api/requests/{request_id}", headers=sender_headers, json={"notify": False}
    )
    assert quiet.status_code == 200, quiet.text
    assert quiet.json()["notify"] is False
    assert quiet.json()["is_open"] is True


async def test_somebody_elses_request_is_not_found(
    client, sender_headers, carrier_headers
):
    """404 and not 403: whether another person's request exists is not a fact
    this endpoint is entitled to confirm."""
    filed = await _file(client, sender_headers)
    r = await client.patch(
        f"/api/requests/{filed.json()['id']}",
        headers=carrier_headers,
        json={"is_open": False},
    )
    assert r.status_code == 404, r.text


async def test_the_public_view_counts_without_naming(
    client, session_maker, sender_headers
):
    """A carrier weighing a route needs the number. Who asked is the senders'
    business, and publishing it would turn a request into a lead list."""
    corridor = uuidlib.uuid4().hex[:3].upper()
    await _file(client, sender_headers, origin=corridor, destination="SVO")

    r = await client.get("/api/requests/open", headers=sender_headers)
    assert r.status_code == 200, r.text
    mine = next(
        (row for row in r.json() if row["origin"] == corridor), None
    )
    assert mine is not None
    assert mine["waiting"] >= 1
    assert set(mine) == {"origin", "destination", "waiting"}

    async with session_maker() as db:
        await db.execute(
            delete(SenderRequest).where(SenderRequest.origin == corridor)
        )
        await db.commit()


async def test_an_expired_window_drops_out_on_its_own(
    client, session_maker, sender_headers, seed_sender
):
    """The filter is the date, so nothing has to sweep — and a request whose
    window has passed stops being demand without anybody deciding it did."""
    corridor = uuidlib.uuid4().hex[:3].upper()
    async with session_maker() as db:
        db.add(
            SenderRequest(
                sender_id=seed_sender.id,
                origin=corridor,
                destination="SVO",
                window_from=date.today() - timedelta(days=30),
                window_to=date.today() - timedelta(days=1),
            )
        )
        await db.commit()

    r = await client.get("/api/requests/open", headers=sender_headers)
    assert all(row["origin"] != corridor for row in r.json())

    async with session_maker() as db:
        await db.execute(
            delete(SenderRequest).where(SenderRequest.origin == corridor)
        )
        await db.commit()


async def test_publishing_a_trip_notifies_only_the_matching_window(
    client, session_maker, sender_headers, carrier_headers, seed_sender
):
    """The window binds. A trip leaving after somebody's last useful day is not
    their trip, and a letter about it teaches them to ignore the next one.
    """
    from app.tasks import notifications as notif

    corridor = uuidlib.uuid4().hex[:3].upper()
    async with session_maker() as db:
        db.add_all(
            [
                SenderRequest(
                    sender_id=seed_sender.id,
                    origin=corridor,
                    destination="SVO",
                    window_from=date.today(),
                    window_to=date.today() + timedelta(days=10),
                ),
            ]
        )
        await db.commit()

    sent: list[tuple[str, str]] = []
    original = notif._notify_user
    notif._notify_user = lambda user, kind, **ctx: sent.append((str(user.id), kind))
    try:
        trip = await client.post(
            "/api/trips",
            headers=carrier_headers,
            json={
                "payment_model": "cash_on_delivery",
                "legs": [
                    {
                        "origin": corridor,
                        "destination": "SVO",
                        "depart_at": (
                            datetime.now(timezone.utc) + timedelta(days=3)
                        ).isoformat(),
                    }
                ],
            },
        )
        assert trip.status_code == 201, trip.text
        notif.notify_corridor_subscribers(trip.json()["id"])
    finally:
        notif._notify_user = original

    assert (str(seed_sender.id), "corridor_trip") in sent

    # …and a trip outside the window reaches nobody.
    sent.clear()
    notif._notify_user = lambda user, kind, **ctx: sent.append((str(user.id), kind))
    try:
        late = await client.post(
            "/api/trips",
            headers=carrier_headers,
            json={
                "payment_model": "cash_on_delivery",
                "legs": [
                    {
                        "origin": corridor,
                        "destination": "SVO",
                        "depart_at": (
                            datetime.now(timezone.utc) + timedelta(days=90)
                        ).isoformat(),
                    }
                ],
            },
        )
        notif.notify_corridor_subscribers(late.json()["id"])
    finally:
        notif._notify_user = original

    assert sent == []

    async with session_maker() as db:
        await db.execute(
            delete(SenderRequest).where(SenderRequest.origin == corridor)
        )
        await db.commit()
