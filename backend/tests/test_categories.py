import uuid as uuidlib
from datetime import datetime, timedelta, timezone


async def _create_trip(client, carrier_headers, categories=("document",)) -> str:
    """T3.11.07 — the trip states what it carries, and the order may ask for
    nothing else (owner's rule 2026-09-08). So a test about a custom category
    publishes it here, on the carrier's side, where capabilities are declared."""
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "legs": [
                {
                    "origin": "MTC",
                    "destination": "DXB",
                    "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                }
            ],
            "capacity": 2.0,
            "allowed_categories": list(categories),
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
    custom = f"custom-{uuidlib.uuid4().hex[:8]}"
    trip_id = await _create_trip(client, carrier_headers, categories=(custom,))
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
    shared = f"shared-{uuidlib.uuid4().hex[:8]}"

    for _ in range(2):
        trip_id = await _create_trip(client, carrier_headers, categories=(shared,))
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


async def test_picker_order_is_the_one_the_owner_named(client):
    """T3.11.07 — documents, clothes, electronics, medicine, animals, art, other.

    Named outright by the owner (2026-09-06) rather than derived, so it is
    asserted as a sequence and not as a handful of pairwise comparisons: the
    point of a stated order is that every position in it is intended.
    """
    resp = await client.get("/api/categories")
    order = [c["name_key"] for c in resp.json() if c["is_default"]]
    assert order == [
        "document",
        "clothing",
        "electronics",
        "medicine",
        "animal",
        "art",
        "other",
    ]


async def test_own_traffic_does_not_reorder_the_picker(client, session_maker):
    """`usage_count` is counted and returned; it no longer decides position.

    It used to outrank `sort_order`, on the argument that this platform's own
    traffic beats a seeded guess. Once the owner named the order, that stopped
    being a tie to break — a picker that quietly rearranges itself as deals
    close is one where a carrier's muscle memory lands on the wrong chip.

    The count is read from the API rather than assumed: `api/deals` increments
    it on every match and the test database is never reset (ENVIRONMENT §8), so
    `document` carries the accumulated total of every deal this suite ever made
    and a hard-coded ceiling is a number that works until it does not.
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

    before = [c["name_key"] for c in (await client.get("/api/categories")).json()]
    art = next(
        c for c in (await client.get("/api/categories")).json() if c["name_key"] == "art"
    )
    ceiling = max(c["usage_count"] for c in (await client.get("/api/categories")).json())

    await set_usage("art", ceiling + 1000)
    try:
        after = [c["name_key"] for c in (await client.get("/api/categories")).json()]
        assert after == before
    finally:
        await set_usage("art", art["usage_count"])
