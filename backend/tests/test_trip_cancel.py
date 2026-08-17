"""T_UX.19 — withdrawing a published trip.

Until this existed a trip could be created and never taken back: plans changed,
the listing stayed up, and senders kept writing to it. The rules worth pinning
are the two refusals rather than the happy path — withdrawing somebody else's
trip, and withdrawing one that another person is already counting on.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import SEED_PASSWORD, make_account, unique_email


def _payload(**overrides):
    body = {
        "origin": "DXB",
        "destination": "JFK",
        "depart_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "capacity": 5.0,
        "allowed_categories": ["document"],
    }
    body.update(overrides)
    return body


async def _publish(client, headers) -> str:
    r = await client.post("/api/trips", headers=headers, json=_payload())
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── the happy path ────────────────────────────────────────────────────────


async def test_carrier_withdraws_own_open_trip(client, carrier_headers):
    trip_id = await _publish(client, carrier_headers)
    r = await client.post(f"/api/trips/{trip_id}/cancel", headers=carrier_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


async def test_withdrawn_trip_leaves_the_public_board(client, carrier_headers):
    """The point of withdrawing: nobody should be able to respond to it any
    more."""
    trip_id = await _publish(client, carrier_headers)
    await client.post(f"/api/trips/{trip_id}/cancel", headers=carrier_headers)

    board = await client.get("/api/trips", headers=carrier_headers)
    assert all(t["id"] != trip_id for t in board.json()["items"])


async def test_withdrawn_trip_stays_in_own_history(client, carrier_headers, seed_carrier):
    """Off the board is not gone. "What have I published" has to keep it, or the
    carrier's own record quietly rewrites itself."""
    trip_id = await _publish(client, carrier_headers)
    await client.post(f"/api/trips/{trip_id}/cancel", headers=carrier_headers)

    history = await client.get(
        "/api/trips",
        headers=carrier_headers,
        params={"carrier_id": str(seed_carrier.id), "status": "all", "limit": 100},
    )
    assert history.status_code == 200, history.text
    mine = next((t for t in history.json()["items"] if t["id"] == trip_id), None)
    assert mine is not None
    assert mine["status"] == "cancelled"


# ── the refusals ──────────────────────────────────────────────────────────


async def test_cannot_withdraw_somebody_elses_trip(client, carrier_headers):
    trip_id = await _publish(client, carrier_headers)

    email = unique_email("other-carrier")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Other"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.post(f"/api/trips/{trip_id}/cancel", headers=hdr)
    assert r.status_code == 403, r.text

    # And it is still on the board — a refused call must not half-succeed.
    board = await client.get("/api/trips", headers=carrier_headers)
    assert any(t["id"] == trip_id for t in board.json()["items"])


async def test_cannot_withdraw_a_matched_trip(
    client, carrier_headers, session_maker, seed_carrier
):
    """A matched trip is somebody else's plan too. Withdrawing it silently
    would cancel their delivery without telling them."""
    from sqlalchemy import update

    from app.models.marketplace import Trip, TripStatus

    trip_id = await _publish(client, carrier_headers)
    async with session_maker() as db:
        await db.execute(
            update(Trip)
            .where(Trip.id == uuid.UUID(trip_id))
            .values(status=TripStatus.matched)
        )
        await db.commit()

    r = await client.post(f"/api/trips/{trip_id}/cancel", headers=carrier_headers)
    assert r.status_code == 409, r.text


async def test_withdrawing_twice_conflicts(client, carrier_headers):
    trip_id = await _publish(client, carrier_headers)
    first = await client.post(f"/api/trips/{trip_id}/cancel", headers=carrier_headers)
    assert first.status_code == 200
    second = await client.post(f"/api/trips/{trip_id}/cancel", headers=carrier_headers)
    assert second.status_code == 409, second.text


async def test_missing_trip_is_404(client, carrier_headers):
    r = await client.post(f"/api/trips/{uuid.uuid4()}/cancel", headers=carrier_headers)
    assert r.status_code == 404


async def test_anonymous_cannot_withdraw(client, carrier_headers):
    trip_id = await _publish(client, carrier_headers)
    r = await client.post(f"/api/trips/{trip_id}/cancel")
    assert r.status_code in (401, 403)


# ── who may ask for non-public statuses ───────────────────────────────────


async def test_status_filter_refused_for_somebody_elses_trips(
    client, sender_headers, seed_carrier
):
    """A withdrawn trip is no longer a public listing. Letting strangers
    enumerate them would publish a carrier's changes of plan."""
    r = await client.get(
        "/api/trips",
        headers=sender_headers,
        params={"carrier_id": str(seed_carrier.id), "status": "cancelled"},
    )
    assert r.status_code == 403, r.text


async def test_status_filter_refused_without_a_carrier(client, carrier_headers):
    r = await client.get(
        "/api/trips", headers=carrier_headers, params={"status": "all"}
    )
    assert r.status_code == 403, r.text


async def test_unknown_status_rejected(client, carrier_headers, seed_carrier):
    r = await client.get(
        "/api/trips",
        headers=carrier_headers,
        params={"carrier_id": str(seed_carrier.id), "status": "grounded"},
    )
    assert r.status_code == 422, r.text


async def test_board_without_status_stays_public(client):
    """No token, no filter: the board is still readable by anyone."""
    r = await client.get("/api/trips")
    assert r.status_code == 200
