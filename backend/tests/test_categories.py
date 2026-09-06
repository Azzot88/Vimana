import uuid as uuidlib
from datetime import datetime, timedelta, timezone


async def _create_trip(client, carrier_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "legs": [
                {
                    "origin": "MTC",
                    "destination": "DXB",
                    "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                }
            ],
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_list_defaults_includes_animal(client):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    keys = {c["name_key"] for c in resp.json()}
    assert "animal" in keys
    assert "document" in keys
    assert "other" in keys


async def test_defaults_marked_is_default(client):
    resp = await client.get("/api/categories")
    body = resp.json()
    animal = next(c for c in body if c["name_key"] == "animal")
    assert animal["is_default"] is True


async def test_search_by_prefix(client):
    resp = await client.get("/api/categories", params={"q": "ani"})
    assert resp.status_code == 200
    keys = {c["name_key"] for c in resp.json()}
    assert "animal" in keys


async def test_new_category_created_on_match(client, carrier_headers, sender_headers):
    trip_id = await _create_trip(client, carrier_headers)
    custom = f"custom-{uuidlib.uuid4().hex[:8]}"
    match = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000002",
                "origin": "MTC",
                "destination": "DXB",
                "category": custom,
                "declared_value": 50.0,
            },
        },
    )
    assert match.status_code == 201, match.text

    resp = await client.get("/api/categories", params={"q": custom})
    body = resp.json()
    assert any(c["name_key"] == custom and c["usage_count"] >= 1 for c in body)


async def test_usage_count_increments_on_reuse(client, carrier_headers, sender_headers):
    trip_id = await _create_trip(client, carrier_headers)
    shared = f"shared-{uuidlib.uuid4().hex[:8]}"

    for _ in range(2):
        trip_id = await _create_trip(client, carrier_headers)
        r = await client.post(
            "/api/deals/match",
            headers=sender_headers,
            json={
                "trip_id": trip_id,
                "order": {
                    "recipient_contact": "+10000000003",
                    "origin": "MTC",
                    "destination": "DXB",
                    "category": shared,
                    "declared_value": 25.0,
                },
            },
        )
        assert r.status_code == 201

    resp = await client.get("/api/categories", params={"q": shared})
    body = resp.json()
    entry = next(c for c in body if c["name_key"] == shared)
    assert entry["usage_count"] >= 2
    assert entry["is_default"] is False


# ── T3.11.07 · the two commonest words on this market ──────────────────────


async def test_parcel_and_clothing_exist(client):
    """«Возьму посылки» is the second most common sentence on this market
    (≈71 % of carrier posts) and «вещи» the third (34 %). Until 0063 neither had
    a key, so neither could be said here or searched for."""
    resp = await client.get("/api/categories")
    keys = {c["name_key"] for c in resp.json()}
    assert "parcel" in keys
    assert "clothing" in keys


async def test_cold_start_order_follows_the_market(client):
    """With every `usage_count` at zero the fallback used to be alphabetical —
    an order about spelling rather than about cargo. `sort_order` seeds the
    market's own frequency instead."""
    resp = await client.get("/api/categories")
    body = [c for c in resp.json() if c["is_default"]]
    order = [c["name_key"] for c in body]
    assert order.index("document") < order.index("parcel")
    assert order.index("parcel") < order.index("clothing")
    assert order.index("clothing") < order.index("medicine")
    assert order.index("other") == len(order) - 1


async def test_own_traffic_outranks_the_seed(client, session_maker):
    """The seed decides the cold start and nothing after it: a category this
    platform actually uses climbs above one the market talks about more.

    Put back afterwards — the test database is never reset (ENVIRONMENT §8), so
    a count left behind would reorder every later test's picker.
    """
    from sqlalchemy import select

    from app.models.marketplace import Category

    async def set_usage(key: str, value: int) -> None:
        async with session_maker() as db:
            row = (
                await db.execute(select(Category).where(Category.name_key == key))
            ).scalar_one()
            row.usage_count = value
            await db.commit()

    await set_usage("art", 999)
    try:
        resp = await client.get("/api/categories")
        order = [c["name_key"] for c in resp.json()]
        assert order[0] == "art"
    finally:
        await set_usage("art", 0)
