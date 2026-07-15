"""T1.26 — receiving address in profile: privacy, cities API, share-in-chat."""
import pytest


async def test_patch_me_saves_receiving_address(client, sender_headers):
    resp = await client.patch(
        "/api/auth/me",
        headers=sender_headers,
        json={
            "receiving_country_iso": "AE",
            "receiving_city": "Dubai",
            "receiving_city_geoname_id": 292223,
            "receiving_street": "Marina Walk 12, apt 305",
            "receiving_postal_code": "00000",
            "receiving_note": "Concierge 24/7, ask for Anna",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["receiving_country_iso"] == "AE"
    assert body["receiving_city"] == "Dubai"
    assert body["receiving_note"] == "Concierge 24/7, ask for Anna"


async def test_country_iso_normalized_to_uppercase(client, sender_headers):
    resp = await client.patch(
        "/api/auth/me",
        headers=sender_headers,
        json={"receiving_country_iso": "ae"},
    )
    assert resp.status_code == 200
    assert resp.json()["receiving_country_iso"] == "AE"


async def test_bad_country_iso_length_rejected(client, sender_headers):
    resp = await client.patch(
        "/api/auth/me",
        headers=sender_headers,
        json={"receiving_country_iso": "USA"},
    )
    assert resp.status_code == 422


async def test_get_me_returns_receiving_address_for_owner(client, sender_headers):
    await client.patch(
        "/api/auth/me",
        headers=sender_headers,
        json={"receiving_country_iso": "US", "receiving_city": "NYC"},
    )
    me = await client.get("/api/auth/me", headers=sender_headers)
    assert me.status_code == 200
    body = me.json()
    assert body["receiving_country_iso"] == "US"
    assert body["receiving_city"] == "NYC"


async def test_admin_users_endpoint_does_not_leak_receiving_address(
    client, session_maker, seed_sender
):
    """Superuser list of all users MUST NOT expose receiving_* fields."""
    from app.models.user import User

    async with session_maker() as db:
        u = await db.get(User, seed_sender.id)
        u.receiving_country_iso = "AE"
        u.receiving_city = "SecretCity"
        u.receiving_street = "SecretStreet 42"
        # Promote to superuser only for this test scope
        original_role = u.role
        u.role = "superuser"
        await db.commit()

    try:
        from tests.conftest import _login
        token = await _login(client, seed_sender.email)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/admin/users?limit=100", headers=headers)
        assert resp.status_code == 200
        for user in resp.json()["items"]:
            assert "receiving_country_iso" not in user
            assert "receiving_city" not in user
            assert "receiving_street" not in user
    finally:
        async with session_maker() as db:
            u = await db.get(User, seed_sender.id)
            u.role = original_role
            u.receiving_country_iso = None
            u.receiving_city = None
            u.receiving_street = None
            await db.commit()


async def test_cities_search_returns_dubai(client):
    resp = await client.get("/api/cities?q=Dub&country=AE")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert any("Dubai" in n for n in names)


async def test_cities_search_empty_q_returns_empty(client):
    resp = await client.get("/api/cities?q=")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_cities_search_multilang_moscow(client):
    """GeoNames alt_names include Cyrillic — search should match."""
    resp = await client.get("/api/cities?q=Москва")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert any("Moscow" in n or "Москва" in n for n in names)


async def test_share_address_in_dealvault_creates_system_message(
    client, sender_headers, carrier_headers, seed_deal
):
    # Set sender's address first
    await client.patch(
        "/api/auth/me",
        headers=sender_headers,
        json={
            "receiving_country_iso": "AE",
            "receiving_city": "Dubai",
            "receiving_street": "Marina Walk",
        },
    )
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/share-address",
        headers=sender_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_system"] is True
    assert body["text"].startswith("📍 SHARED ADDRESS")
    assert "Dubai" in body["text"]
    assert "Marina Walk" in body["text"]


async def test_share_address_without_address_returns_422(
    client, carrier_headers, seed_deal, session_maker, seed_carrier
):
    """Ensure carrier without a set address gets 422 on share."""
    from app.models.user import User

    async with session_maker() as db:
        u = await db.get(User, seed_carrier.id)
        u.receiving_country_iso = None
        await db.commit()

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/share-address",
        headers=carrier_headers,
    )
    assert resp.status_code == 422
    assert "not set" in resp.json()["detail"].lower()


async def test_share_address_in_inquiry_chat(
    client, sender_headers, carrier_headers
):
    # Create trip + inquiry
    from datetime import datetime, timedelta, timezone

    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "ADR",
            "destination": "TST",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]
    inq = await client.post(f"/api/trips/{trip_id}/inquiry", headers=sender_headers)
    inquiry_id = inq.json()["id"]

    # Set sender's address
    await client.patch(
        "/api/auth/me",
        headers=sender_headers,
        json={
            "receiving_country_iso": "US",
            "receiving_city": "New York",
            "receiving_street": "5th Ave 1",
        },
    )

    resp = await client.post(
        f"/api/inquiries/{inquiry_id}/messages/share-address",
        headers=sender_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["text"].startswith("📍 SHARED ADDRESS")
    assert "New York" in body["text"]
