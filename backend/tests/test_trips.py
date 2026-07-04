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
    resp = await client.get("/api/trips")
    assert resp.status_code == 200
    trip_ids = {t["id"] for t in resp.json()}
    assert str(seed_trip.id) in trip_ids


async def test_list_trips_filter_by_origin(client, seed_trip):
    resp = await client.get("/api/trips", params={"origin": "SEED-ORIGIN"})
    assert resp.status_code == 200
    assert any(t["id"] == str(seed_trip.id) for t in resp.json())


async def test_list_trips_filter_no_match(client):
    resp = await client.get("/api/trips", params={"origin": "NONEXISTENT-ZZZ"})
    assert resp.status_code == 200
    assert resp.json() == []
