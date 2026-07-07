"""T1.19 block 5: cursor pagination."""
import uuid as uuidlib
from datetime import datetime, timedelta, timezone


async def _publish_trip(client, carrier_headers, tag: str) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": f"P-{tag}",
            "destination": "PAG",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_trips_pagination_next_cursor_walks_all_items(client, carrier_headers):
    tag = uuidlib.uuid4().hex[:6]
    created_ids = []
    for i in range(5):
        tid = await _publish_trip(client, carrier_headers, f"{tag}-{i}")
        created_ids.append(tid)

    # First page: limit=2
    resp = await client.get(
        "/api/trips", params={"origin": f"P-{tag}", "limit": 2}
    )
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"], "expected next_cursor when more items exist"

    seen = {t["id"] for t in body["items"]}
    cursor = body["next_cursor"]

    # Walk to the end
    while cursor:
        resp = await client.get(
            "/api/trips",
            params={"origin": f"P-{tag}", "limit": 2, "after": cursor},
        )
        body = resp.json()
        seen.update(t["id"] for t in body["items"])
        cursor = body["next_cursor"]

    assert seen == set(created_ids)


async def test_trips_default_limit_returns_bounded_page(client):
    resp = await client.get("/api/trips")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) <= 20  # DEFAULT_LIMIT


async def test_trips_limit_over_max_is_clamped(client):
    resp = await client.get("/api/trips", params={"limit": 9999})
    assert resp.status_code == 422  # Query validation (le=100) rejects out-of-range


async def test_trips_invalid_cursor_returns_empty(client):
    resp = await client.get("/api/trips", params={"after": "not-a-uuid"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_dealvault_pagination_ascending_by_created_at(client, sender_headers, seed_deal):
    # Create 3 messages
    created_ids = []
    for i in range(3):
        r = await client.post(
            f"/api/deals/{seed_deal.id}/dealvault/messages",
            headers=sender_headers,
            json={"text": f"paging msg {i} {uuidlib.uuid4().hex[:4]}", "is_system": False},
        )
        assert r.status_code == 201
        created_ids.append(r.json()["id"])

    # Walk all pages (ASC) collecting ids in order
    ordered_ids: list[str] = []
    cursor: str | None = None
    for _ in range(200):
        params: dict = {"limit": 100}
        if cursor:
            params["after"] = cursor
        r = await client.get(
            f"/api/deals/{seed_deal.id}/dealvault",
            headers=sender_headers,
            params=params,
        )
        body = r.json()
        ordered_ids.extend(m["id"] for m in body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            break

    # Our 3 messages must appear (in the ASC-sorted list) in the order created
    positions = [ordered_ids.index(cid) for cid in created_ids]
    assert positions == sorted(positions)


async def test_deals_pagination_returns_shape(client, sender_headers, seed_deal):
    resp = await client.get("/api/deals", headers=sender_headers, params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "next_cursor" in body
    assert len(body["items"]) <= 5
