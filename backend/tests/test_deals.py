from datetime import datetime, timedelta, timezone


async def _create_open_trip(client, carrier_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "MTC",
            "destination": "DXB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _match_deal(client, sender_headers, trip_id: str) -> str:
    resp = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000001",
                "origin": "MTC",
                "destination": "DXB",
                "category": "document",
                "declared_value": 50.0,
                "description": "Test cargo",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_match_creates_deal(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    assert deal_id


async def test_accept_moves_deal_to_accepted(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await client.post(f"/api/deals/{deal_id}/accept", headers=carrier_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


async def test_accept_forbidden_for_sender(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await client.post(f"/api/deals/{deal_id}/accept", headers=sender_headers)
    assert resp.status_code == 403


async def test_event_handoff_marks_in_transit(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    await client.post(f"/api/deals/{deal_id}/accept", headers=carrier_headers)

    resp = await client.post(
        f"/api/deals/{deal_id}/event",
        headers=carrier_headers,
        json={"event_type": "handoff"},
    )
    assert resp.status_code == 200

    deal_resp = await client.get(f"/api/deals/{deal_id}", headers=carrier_headers)
    assert deal_resp.json()["status"] == "in_transit"


async def test_confirm_closes_deal(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    await client.post(f"/api/deals/{deal_id}/accept", headers=carrier_headers)
    await client.post(
        f"/api/deals/{deal_id}/event",
        headers=carrier_headers,
        json={"event_type": "received"},
    )

    resp = await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


async def test_list_deals_includes_seed(client, sender_headers, seed_deal):
    resp = await client.get("/api/deals", headers=sender_headers)
    assert resp.status_code == 200
    ids = {d["id"] for d in resp.json()}
    assert str(seed_deal.id) in ids


async def test_get_deal_forbidden_for_outsider(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await client.post(
        "/api/auth/register",
        json={
            "email": f"outsider-{deal_id[:8]}@vimana.test",
            "password": "outsider-pass",
            "display_name": "Outsider",
        },
    )
    assert resp.status_code == 201
    login = await client.post(
        "/api/auth/login",
        json={"login": resp.json()["email"], "password": "outsider-pass"},
    )
    outsider_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/deals/{deal_id}", headers=outsider_headers)
    assert resp.status_code == 403
