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
