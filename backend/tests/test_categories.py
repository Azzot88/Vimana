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


async def test_clothing_exists(client):
    """«Вещи» is the third most common thing carriers name (34 % of posts) and
    had no key until 0063."""
    resp = await client.get("/api/categories")
    keys = {c["name_key"] for c in resp.json()}
    assert "clothing" in keys


async def test_retired_categories_leave_the_picker(client):
    """0064 — `parcel` and `gift` are retired, not deleted.

    `parcel` was added off the market analysis (≈71 % of posts say «возьму
    посылки») and taken back out because a parcel is the container, not the
    cargo: everything here is a parcel, so as a category it says nothing. The
    rows stay because trips published with them still need a label.
    """
    resp = await client.get("/api/categories")
    keys = {c["name_key"] for c in resp.json()}
    assert "parcel" not in keys
    assert "gift" not in keys


async def test_cold_start_order_follows_the_market(client):
    """With every `usage_count` at zero the fallback used to be alphabetical —
    an order about spelling rather than about cargo. `sort_order` seeds the
    market's own frequency instead."""
    resp = await client.get("/api/categories")
    order = [c["name_key"] for c in resp.json() if c["is_default"]]
    assert order.index("document") < order.index("clothing")
    assert order.index("clothing") < order.index("electronics")
    assert order.index("electronics") < order.index("medicine")
    assert order.index("other") == len(order) - 1


async def test_own_traffic_outranks_the_seed(client, session_maker):
    """The seed decides the cold start and nothing after it: a category this
    platform actually uses climbs above one the market talks about more.

    Two things this test learned the hard way, both worth keeping.

    The count is read from the API rather than assumed. `api/deals` increments
    `usage_count` on every match, and the test database is never reset
    (ENVIRONMENT §8) — so `document` carries the accumulated total of every deal
    ever created by this suite, and a hard-coded ceiling is a number that works
    until it does not.

    And the claim is "art overtakes document", not "art is first": something
    outside the defaults could legitimately sit on top, and an absolute
    assertion would fail for a reason that has nothing to do with ordering.
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

    before = (await client.get("/api/categories")).json()
    art = next(c for c in before if c["name_key"] == "art")
    # If this ever fails, the ordering is fine and the seed is not: `is_default`
    # sorts first, so a default that lost the flag can never climb.
    assert art["is_default"] is True
    ceiling = max(c["usage_count"] for c in before)

    await set_usage("art", ceiling + 1)
    try:
        order = [c["name_key"] for c in (await client.get("/api/categories")).json()]
        # `document` is seeded first (86.2 % of the market names it) and is the
        # thing the seed would keep on top if the seed still decided.
        assert order.index("art") < order.index("document")
    finally:
        await set_usage("art", art["usage_count"])
