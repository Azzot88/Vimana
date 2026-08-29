"""T1.26 — receiving address in profile: privacy, cities API, share-in-chat."""
import pytest


async def test_admin_users_endpoint_does_not_leak_addresses(
    client, session_maker, seed_sender
):
    """The superuser list of accounts must not carry delivery addresses.

    T_KEYS.1 rewrote this against `receiving_addresses`: the single-address
    `users.receiving_*` columns are gone (migration 0041), but the property is
    not — an address is private whichever table holds it. It currently holds
    "for free", because `UserOut` simply has no address fields; that is exactly
    the kind of guarantee that breaks silently when somebody widens the list
    schema, which is why it keeps a test of its own.

    The four tests that used to live around this one checked the removed
    columns themselves (saving via `PATCH /auth/me`, ISO normalisation, length
    validation, echo in `/me`). Normalisation is covered on the new table by
    `test_addresses.py::test_country_iso_normalized_uppercase`; the rest went
    with the columns.
    """
    from tests.conftest import _login
    from app.models.user import User

    hdr = {"Authorization": f"Bearer {await _login(client, seed_sender.email)}"}
    created = await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Secret", "country_iso": "AE", "city": "SecretCity",
              "street": "SecretStreet 42"},
    )
    assert created.status_code == 201, created.text

    async with session_maker() as db:
        u = await db.get(User, seed_sender.id)
        original_roles = list(u.roles or [])
        u.roles = ["superuser"]
        await db.commit()

    try:
        hdr = {"Authorization": f"Bearer {await _login(client, seed_sender.email)}"}
        listing = await client.get("/api/admin/users", headers=hdr)
        assert listing.status_code == 200, listing.text
        body = listing.text
        assert "SecretCity" not in body
        assert "SecretStreet" not in body
    finally:
        async with session_maker() as db:
            u = await db.get(User, seed_sender.id)
            u.roles = original_roles
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
    # T_KEYS.1 (слой 4) — через текущий путь, а не старые колонки
    # `User.receiving_*`: чтение из них снято, потому что на проде ветка была
    # недостижима. Тест, продолжавший ими пользоваться, проверял снятую дорогу,
    # а не сам обмен адресом.
    await client.post(
        "/api/me/addresses",
        headers=sender_headers,
        json={"label": "Home", "country_iso": "AE", "city": "Dubai", "street": "Marina Walk"},
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
    # T_KEYS.1 — nothing to clear any more: the legacy columns are gone and the
    # carrier has no row in `receiving_addresses`, which is the actual
    # precondition this test is about.

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
    # Явно по id, а не «какой окажется по умолчанию»: сид-пользователь общий
    # для файла, и адрес из соседнего теста остаётся дефолтным. Тест про обмен
    # конкретным адресом и не должен зависеть от порядка запуска.
    addr = await client.post(
        "/api/me/addresses",
        headers=sender_headers,
        json={"label": "NY office", "country_iso": "US", "city": "New York", "street": "5th Ave 1"},
    )
    resp = await client.post(
        f"/api/inquiries/{inquiry_id}/messages/share-address",
        headers=sender_headers,
        json={"address_id": addr.json()["id"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["text"].startswith("📍 SHARED ADDRESS")
    assert "New York" in body["text"]
