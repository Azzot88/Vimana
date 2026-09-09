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


async def test_lookup_returns_cities_and_airports(client):
    resp = await client.get("/api/airports/lookup", params={"q": "dubai"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(c["city"] == "Dubai" and c["iso"] == "AE" for c in body["cities"])
    assert any(a["iata"] == "DXB" for a in body["airports"])


async def test_lookup_empty_query_returns_empty(client):
    resp = await client.get("/api/airports/lookup", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == {"cities": [], "airports": []}


async def test_search_finds_by_cyrillic_moscow(client):
    resp = await client.get("/api/airports", params={"q": "Москва"})
    assert resp.status_code == 200
    body = resp.json()
    isos = {a["country_iso"] for a in body}
    assert "RU" in isos


async def test_lookup_by_cyrillic_moscow_finds_city(client):
    resp = await client.get("/api/airports/lookup", params={"q": "Москва"})
    assert resp.status_code == 200
    cities = resp.json()["cities"]
    assert any(c["city"] == "Moscow" and c["iso"] == "RU" for c in cities)


async def test_lookup_by_kyiv_ukrainian_finds_city(client):
    resp = await client.get("/api/airports/lookup", params={"q": "Київ"})
    assert resp.status_code == 200
    cities = resp.json()["cities"]
    assert any(c["iso"] == "UA" for c in cities)


def test_alternate_city_names_still_match_after_precomputing_case():
    """T_PERF.1 — search compares against lower-cased copies built at load.

    The alternate-name index is what lets OpenFlights' "Kiev" find the GeoNames
    record spelled "Kyiv", and it is the one place where the pre-computation
    could have silently dropped a field instead of lower-casing it.
    """
    from app.core.airports import search

    # "Київ" is only reachable through the alternate-name list (the airport's
    # own city field says "Kiev"); "KIEV" additionally proves the query is
    # folded against a pre-lowered field rather than a freshly lowered one.
    for spelling in ("Київ", "KIEV"):
        hits = search(spelling, limit=10)
        assert any(a.country_iso == "UA" for a in hits), spelling


def test_static_aggregates_are_computed_once():
    """The airport table cannot change at runtime, so these are cached rather
    than recomputed per request; identity is the cheapest proof."""
    from app.core.airports import list_cities, list_countries

    assert list_countries() is list_countries()
    assert list_cities("AE") is list_cities("AE")


async def test_airports_in_dubai_sorted_dxb_first(client):
    resp = await client.get(
        "/api/airports/by-city", params={"country": "AE", "city": "Dubai"}
    )
    assert resp.status_code == 200
    iatas = [a["iata"] for a in resp.json()]
    assert iatas[0] == "DXB", f"expected DXB first, got {iatas}"


# ── T3.11.07 · what the picker offers before anything is typed ─────────────


async def test_popular_is_open_without_auth(client):
    """Same posture as the rest of this router: every code it can return is
    already visible on the public board."""
    resp = await client.get("/api/airports/popular")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_popular_counts_both_ends_of_a_flight(client, carrier_headers):
    """A corridor is busy in both directions. Counting departures only would
    rank the return leg at zero, and the picker would offer half a market."""
    from datetime import datetime, timedelta, timezone

    depart = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
    created = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={"payment_model": "cash_on_delivery", "legs": [{"origin": "DXB", "destination": "JFK", "depart_at": depart}]},
    )
    assert created.status_code == 201, created.text

    resp = await client.get("/api/airports/popular", params={"limit": 20})
    codes = [a["iata"] for a in resp.json()]
    assert "DXB" in codes
    assert "JFK" in codes


async def test_popular_drops_codes_that_are_not_airports(client, carrier_headers):
    """Trips are published with hand-typed codes too (and every fixture in this
    suite does it). A code with no airport behind it cannot be rendered as a
    suggestion, so it is skipped rather than returned half-filled."""
    from datetime import datetime, timedelta, timezone

    depart = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
    await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "legs": [
                {"origin": "ZZQ", "destination": "ZZW", "depart_at": depart}
            ]
        },
    )
    resp = await client.get("/api/airports/popular", params={"limit": 20})
    codes = [a["iata"] for a in resp.json()]
    assert "ZZQ" not in codes
    assert "ZZW" not in codes


async def test_popular_respects_the_limit(client):
    resp = await client.get("/api/airports/popular", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


# ── T3.11.07 · country names have to resolve, or three things go quiet ──────


def test_every_country_resolves_to_an_iso():
    """A country name with no ISO code costs an airport three things at once.

    It keeps working in the picker, and quietly loses its GeoNames alt-names
    (so it can only be found by its English name), its postal catalogue and its
    payment catalogue. Nothing raises — that is the whole problem.

    This is how Turkey was found: ISO renamed it to Türkiye in 2022, pycountry
    followed, and `"Turkey"` — what OpenFlights writes — stopped matching in a
    library upgrade. Every Turkish airport went half-missing and stayed that way
    until the owner could not add Istanbul.

    The assertion prints the offenders, so the fix is one line in
    `_COUNTRY_ALIASES` per name.
    """
    from app.core.airports import unresolved_countries

    missing = unresolved_countries()
    assert missing == [], f"no ISO for: {missing}"


def test_istanbul_is_findable_by_code_and_by_name():
    """The airport the owner could not add. Both spellings of the query, and
    the country code, because it was the empty code that broke the rest."""
    from app.core.airports import search

    by_code = search("IST")
    assert any(a.iata == "IST" for a in by_code), [a.iata for a in by_code]

    ist = next(a for a in by_code if a.iata == "IST")
    assert ist.country_iso == "TR"
    assert ist.city == "Istanbul"

    by_name = search("Istanbul")
    assert any(a.iata == "IST" for a in by_name), [a.iata for a in by_name]


def test_turkish_airports_are_findable_in_russian():
    """The GeoNames alt-names come from the country index, which is keyed by
    ISO — so an unresolved country loses every language but English. Cyrillic is
    the case that matters here: this market writes «Стамбул», not «Istanbul»."""
    from app.core.airports import search

    found = search("Стамбул")
    assert any(a.iata in ("IST", "SAW") for a in found), [a.iata for a in found]
