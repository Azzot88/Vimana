"""T3.11.07 — the two country-scoped catalogues the trip form offers.

Postal services answer "who carries it onward after I land"; payment systems
answer "how do we settle if not on the platform". Same shape, different
subjects, one module behind them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


# ── postal services ───────────────────────────────────────────────────────


async def test_postal_services_are_scoped_to_the_destination(client):
    """Onward shipping happens after landing, so the country is where the
    flight arrives: New York gets USPS, Istanbul gets PTT."""
    us = (await client.get("/api/postal-services", params={"country": "US"})).json()
    tr = (await client.get("/api/postal-services", params={"country": "TR"})).json()
    assert "usps" in {s["code"] for s in us}
    assert "ptt" in {s["code"] for s in tr}
    assert "usps" not in {s["code"] for s in tr}


async def test_only_local_services_are_offered(client):
    """Owner's decision 2026-09-06: no global bucket.

    Somebody posting a parcel inside Turkey ships with what is near them, and a
    list topped by three international couriers describes a business rather than
    a person with one pick-up point down the road.
    """
    codes = {
        s["code"]
        for s in (
            await client.get("/api/postal-services", params={"country": "TR"})
        ).json()
    }
    assert "ptt" in codes
    assert "dhl" not in codes
    assert "fedex" not in codes


async def test_couriers_are_filed_where_they_deliver_domestically(client):
    """The consequence of dropping the global bucket, and the honest place for
    them: UPS and FedEx carry parcels inside the United States, DHL inside
    Germany. Filed under those countries rather than appended to all of them."""
    us = {
        s["code"]
        for s in (
            await client.get("/api/postal-services", params={"country": "US"})
        ).json()
    }
    de = {
        s["code"]
        for s in (
            await client.get("/api/postal-services", params={"country": "DE"})
        ).json()
    }
    assert {"usps", "ups", "fedex"} <= us
    assert "dhl_de" in de
    assert "ups" not in de


async def test_postal_without_a_country_answers_with_nothing(client):
    """"Somewhere, I have not said where yet" has no local services in it. The
    form falls back to free text, which is the honest answer."""
    assert (await client.get("/api/postal-services")).json() == []


async def test_unknown_country_does_not_fail(client):
    """A trip into a country the catalogue does not cover still publishes: the
    picker is empty and the carrier types the service by hand. This catalogue
    has no external source and must not be able to tell them they are wrong."""
    body = (await client.get("/api/postal-services", params={"country": "ZZ"})).json()
    assert body == []


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


async def test_arrival_country_comes_before_departure(client):
    """Both ends, and in that order (owner's decision 2026-09-06).

    Settlement most often happens where the cargo changes hands — at the end of
    the flight — so the arrival country is offered first; but a carrier who
    lives at the departure end still needs their own systems offered rather than
    typed out. The order is the answer here, not just the contents: mixing the
    two countries would bury the systems of the place the parcel is going.
    """
    codes = [
        s["code"]
        for s in (
            await client.get(
                "/api/payment-systems", params={"arrival": "US", "departure": "BY"}
            )
        ).json()
    ]
    assert codes.index("zelle") < codes.index("erip")
    # Global names wait until both countries have had their turn.
    assert codes.index("erip") < codes.index("wise")


async def test_a_country_alone_still_answers(client):
    """The form asks before the route is finished, and half a route is a real
    state rather than an error."""
    by = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"arrival": "BY"})
        ).json()
    }
    us = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"arrival": "US"})
        ).json()
    }
    assert "erip" in by
    assert "erip" not in us
    assert "zelle" in us
    assert "zelle" not in by


async def test_cash_is_a_system_not_a_settlement_model(client):
    """The correction that produced 0066: cash is one of the ways people settle
    outside the platform, not a peer of "transfer"."""
    codes = {
        s["code"]
        for s in (await client.get("/api/payment-systems")).json()
    }
    assert "cash" in codes


async def test_a_system_is_never_offered_twice(client):
    """Both layers name some of the same services, and the picker must show
    each once."""
    body = (
        await client.get("/api/payment-systems", params={"arrival": "DE"})
    ).json()
    codes = [s["code"] for s in body]
    names = [s["name"].casefold() for s in body]
    assert len(codes) == len(set(codes))
    assert len(names) == len(set(names))


async def test_payment_without_a_country_answers_globally(client):
    codes = {s["code"] for s in (await client.get("/api/payment-systems")).json()}
    assert "cash" in codes
    assert "wise" in codes
    assert "sbp" not in codes


# ── the vendored HodlHodl layer ───────────────────────────────────────────


async def test_vendored_catalogue_adds_breadth(client):
    """Owner's decision 2026-09-06: HodlHodl's public catalogue is stored in the
    image and merged under ours. 432 methods across 114 countries."""
    body = (
        await client.get("/api/payment-systems", params={"arrival": "TH"})
    ).json()
    assert any(s["code"].startswith("hh:") for s in body)


async def test_our_layer_covers_what_theirs_does_not(client):
    """The reason the two layers exist rather than one.

    Measured the day it was fetched: HodlHodl holds **nothing** for Russia, one
    entry for the United States, and neither Zelle nor Venmo — it serves bitcoin
    P2P and does not operate in every market we fly to. Replacing our list with
    theirs would have made our launch corridor worse, not better.
    """
    ru = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"arrival": "RU"})
        ).json()
    }
    us = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"arrival": "US"})
        ).json()
    }
    # Neither of these comes from the vendored catalogue — that is the point.
    assert "sbp" in ru
    assert "zelle" in us


async def test_our_entry_wins_when_both_name_the_same_service(client):
    """Wise is in both lists. It must appear once, and as ours — a stored value
    should not say `hh:` for something we curate."""
    body = (
        await client.get("/api/payment-systems", params={"arrival": "GB"})
    ).json()
    wise = [s for s in body if s["name"].casefold() == "wise"]
    assert len(wise) == 1
    assert wise[0]["code"] == "wise"


async def test_vendored_codes_are_namespaced(client):
    """`hh:` prefixes every vendored row so it can never collide with ours and
    so a stored answer says where it came from."""
    body = (await client.get("/api/payment-systems", params={"arrival": "TH"})).json()
    for entry in body:
        assert entry["code"].startswith("hh:") or ":" not in entry["code"]


def test_vendored_file_records_where_it_came_from():
    """The provenance and the legal note travel with the data, not with the
    code that reads it: a copy of somebody else's catalogue that does not say
    whose it is becomes ours by accident on the first refactor."""
    import json

    from app.core.directories import HODLHODL_PATH

    raw = json.loads(HODLHODL_PATH.read_text(encoding="utf-8"))
    source = raw["_source"]
    assert source["origin"].startswith("https://hodlhodl.com/")
    assert source["fetched_at"]
    assert source["note"]
    assert len(raw["payment_methods"]) > 300


# ── the monthly check ─────────────────────────────────────────────────────


def test_monthly_check_reports_and_never_writes(monkeypatch):
    """The whole design of the check in one test.

    The catalogue was vendored so that changes to it are reviewable; a copy that
    rewrites itself on a schedule is a copy nobody has read. So the task
    produces an offer and the file is not touched, whatever upstream says.
    """
    import json

    from app.core.directories import HODLHODL_PATH
    from app.tasks import directories as task

    before = HODLHODL_PATH.read_bytes()
    stored = json.loads(before)
    kept = stored["payment_methods"][:2]

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "payment_methods": kept
                + [{"id": "999999", "name": "Invented Pay", "country_codes": ["ZZ"]}]
            }

    monkeypatch.setattr(task.httpx, "get", lambda *a, **kw: _Response())

    result = task.check_payment_catalogue()
    assert result["reachable"] is True
    assert "Invented Pay" in result["added"]
    assert result["removed"]
    assert HODLHODL_PATH.read_bytes() == before


def test_unreachable_upstream_is_not_a_failure(monkeypatch):
    """The stored copy is still serving every request, which is the entire
    reason it is stored. An unreachable third party is one log line."""
    from app.tasks import directories as task

    def _boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(task.httpx, "get", _boom)
    assert task.check_payment_catalogue() == {"reachable": False}


def test_the_check_is_registered_with_the_worker():
    """`worker.py` carries a comment about the day beat emitted into a void for
    weeks because a task module was not listed. This is that guard."""
    from app.worker import celery_app

    assert "app.tasks.directories.check_payment_catalogue" in celery_app.tasks
    scheduled = {
        entry["task"] for entry in celery_app.conf.beat_schedule.values()
    }
    assert "app.tasks.directories.check_payment_catalogue" in scheduled


# ── T3.11.07 · three systems are offered on every corridor ─────────────────


def test_crypto_is_offered_whatever_the_corridor():
    """BTC, USDT and ZEC settle the same way at both ends of every route, which
    is why a P2P carrier reaches for them when the two countries share no rail —
    the commonest case on this market. Owner's decision 2026-09-06."""
    from app.core.directories import payment_systems

    for arrival, departure in (("RU", "AE"), ("US", "PL"), (None, None), ("XX", "YY")):
        codes = [e["code"] for e in payment_systems(arrival, departure)]
        assert {"btc", "usdt", "zec"} <= set(codes), (arrival, departure, codes)


def test_crypto_comes_first_so_it_cannot_fall_off_the_visible_chips():
    """Appended last, as it was, it dropped past the form's visible chips the
    moment both countries had entries. "Always offered" and "offered if the
    list is short enough" are different promises."""
    from app.core.directories import payment_systems

    codes = [e["code"] for e in payment_systems("RU", "AE")]
    assert codes[:3] == ["btc", "usdt", "zec"], codes[:6]


def test_bitcoin_is_not_listed_twice():
    """`bitcoin`/«Bitcoin» and `btc`/«BTC» are one thing written two ways, and a
    picker offering both asks the carrier to choose between them."""
    from app.core.directories import payment_systems

    names = [e["name"].casefold() for e in payment_systems("US", "RU")]
    assert "bitcoin" not in names, names


# ── T3.11.07 · the picker orders itself by what carriers actually chose ────


async def test_postal_services_are_ordered_by_real_use(client, carrier_headers):
    """Owner's «можно», unblocked once the picker was wired to the form.

    The file's order is a seed — how often the market *names* a service — and a
    seed only has to answer the cold start. Once real trips carry real choices
    those outrank it, the same arrangement as `Category.usage_count` beating
    `sort_order`.
    """
    seeded = await client.get("/api/postal-services", params={"country": "US"})
    assert seeded.status_code == 200, seeded.text
    names = [e["name"] for e in seeded.json()]
    if len(names) < 2:
        import pytest

        pytest.skip("the US slice needs two services for order to mean anything")

    # Pick the one the file puts **last** and have real trips choose it.
    underdog = names[-1]
    for _ in range(3):
        trip = await client.post(
            "/api/trips",
            headers=carrier_headers,
            json={
                "payment_model": "cash_on_delivery",
                "legs": [
                    {
                        "origin": "DXB",
                        "destination": "JFK",
                        "depart_at": (
                            datetime.now(timezone.utc) + timedelta(days=5)
                        ).isoformat(),
                    }
                ],
                "handover_destination": {
                    "methods": ["local_post"],
                    "postal_services": [underdog],
                },
            },
        )
        assert trip.status_code == 201, trip.text

    reordered = await client.get("/api/postal-services", params={"country": "US"})
    assert reordered.json()[0]["name"] == underdog

    # Nothing was hidden: a picker that dropped an unused service could not
    # describe the one pick-up point down somebody's road.
    assert {e["name"] for e in reordered.json()} == set(names)


async def test_a_country_nobody_flies_to_keeps_the_seeded_order(client):
    """No trips, no counts, no change — a cold start reads exactly as before."""
    first = await client.get("/api/postal-services", params={"country": "PL"})
    second = await client.get("/api/postal-services", params={"country": "PL"})
    assert [e["name"] for e in first.json()] == [e["name"] for e in second.json()]
