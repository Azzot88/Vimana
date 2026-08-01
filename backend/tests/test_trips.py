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
    """The date filter is a half-open UTC day, not a cast on the column."""
    depart = (datetime.now(timezone.utc) + timedelta(days=11)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "DTFLT",
            "destination": "DTFLT-DEST",
            "depart_at": depart.isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    assert created.status_code == 201
    trip_id = created.json()["id"]

    same_day = await client.get(
        "/api/trips",
        params={"origin": "DTFLT", "date": depart.date().isoformat()},
    )
    assert same_day.status_code == 200
    assert any(t["id"] == trip_id for t in same_day.json()["items"])

    day_before = await client.get(
        "/api/trips",
        params={
            "origin": "DTFLT",
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
