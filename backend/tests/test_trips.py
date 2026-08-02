from datetime import datetime, timedelta, timezone


async def test_create_trip_as_carrier(client, carrier_headers):
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "AAA",
            "destination": "BBB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 3.5,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["origin"] == "AAA"
    assert body["destination"] == "BBB"
    assert body["status"] == "open"


async def test_create_trip_forbidden_for_sender(client, sender_headers):
    resp = await client.post(
        "/api/trips",
        headers=sender_headers,
        json={
            "origin": "XXX",
            "destination": "YYY",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "capacity": 1.0,
        },
    )
    assert resp.status_code == 403


async def test_list_trips_returns_seed(client, seed_trip):
    # Filter by seed origin to guarantee it's on the first page
    resp = await client.get("/api/trips", params={"origin": "SEED-ORIGIN"})
    assert resp.status_code == 200
    trip_ids = {t["id"] for t in resp.json()["items"]}
    assert str(seed_trip.id) in trip_ids


async def test_list_trips_filter_by_origin(client, seed_trip):
    resp = await client.get("/api/trips", params={"origin": "SEED-ORIGIN"})
    assert resp.status_code == 200
    assert any(t["id"] == str(seed_trip.id) for t in resp.json()["items"])


async def test_trip_route_is_normalised_on_write(client, carrier_headers):
    """T_PERF.1 — the column holds one canonical form.

    The filter compares codes exactly, so a trip stored as `dxb` would be
    invisible to every search for `DXB`. `AirportSelect` sends upper-case
    already; a direct POST does not have to, and deciding the shape on write is
    what keeps every reader from having to.
    """
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": " nrm ",
            "destination": "nrd",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["origin"] == "NRM"
    assert resp.json()["destination"] == "NRD"

    found = await client.get("/api/trips", params={"origin": "NRM"})
    assert any(t["id"] == resp.json()["id"] for t in found.json()["items"])


async def test_list_trips_filter_origin_is_exact_not_substring(client, seed_trip):
    """T_PERF.1 — the filter matches a code, not a fragment of one.

    `ilike '%SEED%'` used to return the seed trip here. Beyond being unable to
    use an index, it meant `?origin=A` matched every airport with an A in it.
    """
    resp = await client.get("/api/trips", params={"origin": "SEED"})
    assert resp.status_code == 200
    assert all(t["id"] != str(seed_trip.id) for t in resp.json()["items"])


async def test_list_trips_filter_origin_is_case_insensitive(client, seed_trip):
    """A hand-typed lower-case code still finds the trip — the query is
    normalised, the stored value comes from the airport picker already upper."""
    resp = await client.get("/api/trips", params={"origin": "seed-origin"})
    assert resp.status_code == 200
    assert any(t["id"] == str(seed_trip.id) for t in resp.json()["items"])


async def test_list_trips_filter_by_departure_date(client, carrier_headers):
    """The date filter is a half-open UTC day, not a cast on the column.

    The origin is unique per run on purpose. With a fixed one this test failed
    a day after it was written: trips are never deleted, so yesterday's
    "now + 11 days" is today's "day before" — and they matched the negative
    assertion entirely legitimately. A test that depends on the calendar date
    it runs on has to scope itself to its own run.
    """
    import uuid as uuidlib

    origin = f"DT{uuidlib.uuid4().hex[:6].upper()}"
    depart = (datetime.now(timezone.utc) + timedelta(days=11)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": origin,
            "destination": f"{origin}-DEST",
            "depart_at": depart.isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    assert created.status_code == 201
    trip_id = created.json()["id"]

    same_day = await client.get(
        "/api/trips",
        params={"origin": origin, "date": depart.date().isoformat()},
    )
    assert same_day.status_code == 200
    assert any(t["id"] == trip_id for t in same_day.json()["items"])

    day_before = await client.get(
        "/api/trips",
        params={
            "origin": origin,
            "date": (depart.date() - timedelta(days=1)).isoformat(),
        },
    )
    assert day_before.status_code == 200
    assert day_before.json()["items"] == []


async def test_list_trips_filter_no_match(client):
    resp = await client.get("/api/trips", params={"origin": "NONEXISTENT-ZZZ"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_a_retired_carrier_is_marked_on_the_listing(client, carrier_headers, session_maker):
    """T3.17 — a lost key means the account can be signed into but can no longer
    act. Finding that out after choosing a carrier is finding it out too late."""
    import uuid as uuidlib

    from app.models.user import User

    # Unique per run for the same reason as the date test above: nothing is
    # deleted, and a fixed origin turns leftovers into false positives.
    origin = f"LST{uuidlib.uuid4().hex[:6].upper()}"
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": origin,
            "destination": f"{origin}-D",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    assert created.status_code == 201
    carrier_id = created.json()["carrier_id"]

    listed = await client.get("/api/trips", params={"origin": origin})
    assert listed.json()["items"][0]["carrier_key_lost"] is False

    async with session_maker() as db:
        user = await db.get(User, uuidlib.UUID(carrier_id))
        user.key_lost_at = datetime.now(timezone.utc)
        await db.commit()

    try:
        after = await client.get("/api/trips", params={"origin": origin})
        assert after.json()["items"][0]["carrier_key_lost"] is True
    finally:
        # The seed carrier is shared across the suite — a retired flag left
        # behind would quietly change what every other test sees.
        async with session_maker() as db:
            user = await db.get(User, uuidlib.UUID(carrier_id))
            user.key_lost_at = None
            await db.commit()
