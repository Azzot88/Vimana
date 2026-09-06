"""T3.11.07 — the two country-scoped catalogues the trip form offers.

Postal services answer "who carries it onward after I land"; payment systems
answer "how do we settle if not on the platform". Same shape, different
subjects, one module behind them.
"""
from __future__ import annotations


# ── postal services ───────────────────────────────────────────────────────


async def test_postal_services_are_scoped_to_the_destination(client):
    """Onward shipping happens after landing, so the country is where the
    flight arrives: New York gets USPS, Istanbul gets PTT."""
    us = (await client.get("/api/postal-services", params={"country": "US"})).json()
    tr = (await client.get("/api/postal-services", params={"country": "TR"})).json()
    assert "usps" in {s["code"] for s in us}
    assert "ptt" in {s["code"] for s in tr}
    assert "usps" not in {s["code"] for s in tr}


async def test_local_services_come_before_the_global_couriers(client):
    """Somebody posting inside Turkey wants PTT above DHL; the global names are
    the ones they would have thought of anyway."""
    body = (await client.get("/api/postal-services", params={"country": "TR"})).json()
    codes = [s["code"] for s in body]
    assert codes.index("ptt") < codes.index("dhl")


async def test_global_couriers_are_offered_everywhere(client):
    for country in ("US", "RU", "TH"):
        codes = {
            s["code"]
            for s in (
                await client.get("/api/postal-services", params={"country": country})
            ).json()
        }
        assert {"dhl", "fedex", "ups"} <= codes, country


async def test_no_country_answers_with_the_global_set(client):
    """The honest answer to "somewhere, I have not said where yet"."""
    body = (await client.get("/api/postal-services")).json()
    assert {s["code"] for s in body} == {"dhl", "fedex", "ups"}


async def test_unknown_country_does_not_fail(client):
    """A trip into a country the catalogue does not cover still publishes; the
    form keeps free text for exactly this."""
    body = (await client.get("/api/postal-services", params={"country": "ZZ"})).json()
    assert {s["code"] for s in body} == {"dhl", "fedex", "ups"}


async def test_marketplaces_are_not_postal_services(client):
    """Collecting an order by its number is a purchase-and-collect errand and
    already has its own key, `marketplace_pickup`. Listing Ozon here would let a
    carrier answer one question in two vocabularies."""
    body = (await client.get("/api/postal-services", params={"country": "RU"})).json()
    codes = {s["code"] for s in body}
    assert "ozon" not in codes
    assert "wildberries" not in codes
    assert "cdek" in codes


async def test_postal_catalogue_is_open_without_a_token(client):
    r = await client.get("/api/postal-services", params={"country": "RU"})
    assert r.status_code == 200


# ── payment systems ───────────────────────────────────────────────────────


async def test_payment_systems_span_both_ends_of_the_route(client):
    """Payment is between two people who are, by the nature of this product, in
    different countries. Either end's systems may be the one they agree on."""
    body = (
        await client.get("/api/payment-systems", params={"countries": "RU,US"})
    ).json()
    codes = {s["code"] for s in body}
    assert "sbp" in codes
    assert "zelle" in codes


async def test_cash_is_a_system_not_a_settlement_model(client):
    """The correction that produced 0066: cash is one of the ways people settle
    outside the platform, not a peer of "transfer"."""
    codes = {
        s["code"]
        for s in (await client.get("/api/payment-systems")).json()
    }
    assert "cash" in codes


async def test_payment_systems_are_not_repeated_across_countries(client):
    """Several countries list SEPA; the picker must not show it four times."""
    body = (
        await client.get(
            "/api/payment-systems", params={"countries": "DE,FR,IT,ES"}
        )
    ).json()
    codes = [s["code"] for s in body]
    assert len(codes) == len(set(codes))


async def test_no_countries_answers_with_the_global_set(client):
    codes = {s["code"] for s in (await client.get("/api/payment-systems")).json()}
    assert "cash" in codes
    assert "wise" in codes
    assert "sbp" not in codes
