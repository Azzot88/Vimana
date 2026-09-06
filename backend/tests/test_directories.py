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


async def test_postal_without_a_country_answers_globally(client):
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


async def test_payment_systems_are_a_plain_substitution_by_country(client):
    """One country, not both ends of the route (owner's correction 2026-09-06).

    The airport says the country, the country says the systems: a flight out of
    Minsk offers Belarusian systems, a flight out of New York American ones. The
    trip states which systems **this carrier** accepts, and a carrier settles
    where they are.
    """
    by = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"country": "BY"})
        ).json()
    }
    us = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"country": "US"})
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
        await client.get("/api/payment-systems", params={"country": "DE"})
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
        await client.get("/api/payment-systems", params={"country": "TH"})
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
            await client.get("/api/payment-systems", params={"country": "RU"})
        ).json()
    }
    us = {
        s["code"]
        for s in (
            await client.get("/api/payment-systems", params={"country": "US"})
        ).json()
    }
    # Neither of these comes from the vendored catalogue — that is the point.
    assert "sbp" in ru
    assert "zelle" in us


async def test_our_entry_wins_when_both_name_the_same_service(client):
    """Wise is in both lists. It must appear once, and as ours — a stored value
    should not say `hh:` for something we curate."""
    body = (
        await client.get("/api/payment-systems", params={"country": "GB"})
    ).json()
    wise = [s for s in body if s["name"].casefold() == "wise"]
    assert len(wise) == 1
    assert wise[0]["code"] == "wise"


async def test_vendored_codes_are_namespaced(client):
    """`hh:` prefixes every vendored row so it can never collide with ours and
    so a stored answer says where it came from."""
    body = (await client.get("/api/payment-systems", params={"country": "TH"})).json()
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
