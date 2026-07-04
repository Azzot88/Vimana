async def test_search_by_iata(client):
    resp = await client.get("/api/airports", params={"q": "DXB"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(a["iata"] == "DXB" and a["country"] == "United Arab Emirates" for a in body)


async def test_search_by_city_substring(client):
    resp = await client.get("/api/airports", params={"q": "dubai"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    assert any("Dubai" in a["city"] for a in body)


async def test_search_empty_query_returns_empty(client):
    resp = await client.get("/api/airports", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_returns_at_most_10(client):
    resp = await client.get("/api/airports", params={"q": "a"})
    assert resp.status_code == 200
    assert len(resp.json()) <= 10


async def test_nearest_dubai(client):
    resp = await client.get(
        "/api/airports/nearest", params={"lat": 25.2532, "lon": 55.3657, "limit": 3}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert body[0]["iata"] == "DXB"


async def test_nearest_default_limit_is_5(client):
    resp = await client.get(
        "/api/airports/nearest", params={"lat": 40.6413, "lon": -73.7781}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 5


async def test_nearest_rejects_invalid_coords(client):
    resp = await client.get(
        "/api/airports/nearest", params={"lat": 200, "lon": 0}
    )
    assert resp.status_code == 422


async def test_countries_returns_iso_codes(client):
    resp = await client.get("/api/airports/countries")
    assert resp.status_code == 200
    body = resp.json()
    isos = {c["iso"] for c in body}
    assert "AE" in isos
    assert "US" in isos
    assert all(len(c["iso"]) == 2 for c in body)
    assert all(c["count"] > 0 for c in body)


async def test_cities_by_country_ae(client):
    resp = await client.get("/api/airports/cities", params={"country": "AE"})
    assert resp.status_code == 200
    cities = {c["city"] for c in resp.json()}
    assert "Dubai" in cities


async def test_by_city_dubai_ae(client):
    resp = await client.get(
        "/api/airports/by-city", params={"country": "AE", "city": "Dubai"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any(a["iata"] == "DXB" for a in body)
    assert all(a["country_iso"] == "AE" for a in body)


async def test_by_city_unknown_returns_404(client):
    resp = await client.get(
        "/api/airports/by-city", params={"country": "AE", "city": "Nonexistent City"}
    )
    assert resp.status_code == 404


async def test_country_iso_populated_for_dxb(client):
    resp = await client.get("/api/airports", params={"q": "DXB"})
    body = resp.json()
    dxb = next(a for a in body if a["iata"] == "DXB")
    assert dxb["country_iso"] == "AE"
