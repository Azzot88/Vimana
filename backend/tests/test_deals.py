from datetime import datetime, timedelta, timezone
from tests.conftest import make_account


async def _create_open_trip(client, carrier_headers) -> str:
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
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _match_deal(client, sender_headers, trip_id: str) -> str:
    resp = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000001",
                "origin": "MTC",
                "destination": "DXB",
                "category": "document",
                "declared_value": 50.0,
                "description": "Test cargo",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_match_creates_deal(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    assert deal_id


async def test_agreeing_terms_moves_deal_to_accepted(
    client, carrier_headers, sender_headers
):
    """T3.35 — the only route to `accepted`. The bare `/accept` endpoint is
    gone: a status reachable two ways eventually gets reached the way nobody
    planned for."""
    from tests.conftest import agree_terms

    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    await agree_terms(client, sender_headers, carrier_headers, deal_id)

    resp = await client.get(f"/api/deals/{deal_id}", headers=carrier_headers)
    assert resp.json()["status"] == "accepted"


async def test_bare_accept_endpoint_is_gone(client, carrier_headers, sender_headers):
    """Pinned deliberately: leaving the old route mounted would keep the second
    path alive for anyone still calling it."""
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await client.post(f"/api/deals/{deal_id}/accept", headers=carrier_headers)
    assert resp.status_code in (404, 405)


async def test_own_proposal_cannot_be_accepted_by_its_author(
    client, carrier_headers, sender_headers
):
    """The replacement for "the sender may not accept": agreement takes two."""
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    proposal = await client.post(
        f"/api/deals/{deal_id}/terms",
        headers=sender_headers,
        json={"weight_kg": 2, "price_total": 60, "declared_value": 500},
    )
    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{proposal.json()['id']}/ack",
        headers=sender_headers,
        json={"decision": "accepted"},
    )
    assert resp.status_code == 403


async def test_event_handoff_marks_in_transit(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    from tests.conftest import agree_terms

    await agree_terms(client, sender_headers, carrier_headers, deal_id)

    resp = await client.post(
        f"/api/deals/{deal_id}/event",
        headers=carrier_headers,
        json={"event_type": "handoff"},
    )
    assert resp.status_code == 200

    deal_resp = await client.get(f"/api/deals/{deal_id}", headers=carrier_headers)
    assert deal_resp.json()["status"] == "in_transit"


async def test_confirm_closes_deal(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)
    from tests.conftest import agree_terms

    await agree_terms(client, sender_headers, carrier_headers, deal_id)
    await client.post(
        f"/api/deals/{deal_id}/event",
        headers=carrier_headers,
        json={"event_type": "received"},
    )

    resp = await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


async def test_list_deals_returns_my_own_deal(
    client, sender_headers, carrier_headers
):
    """A deal I am party to appears in my list, newest first.

    Rewritten 2026-08-08. It used to look for the *seed* deal by walking the
    cursor forward with a 50-page safety cap — and the cap had itself been
    added on 2026-07-06 for this same failure. Both were treatments of the
    symptom: the seed deal is the oldest row in a newest-first list, and every
    suite run pushes it one page further away. A test that needs a larger
    constant every month is measuring the size of the test database, not the
    endpoint.

    A freshly created deal is on the first page by construction, and stays
    there no matter how much history accumulates.
    """
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await client.get("/api/deals", headers=sender_headers, params={"limit": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert "next_cursor" in body
    assert deal_id in {d["id"] for d in body["items"]}


async def test_seed_deal_is_still_readable_by_its_sender(
    client, sender_headers, seed_deal
):
    """The other half of what the old test covered: the seed deal is mine.

    Asked by id rather than found by paging, so it answers the question the
    name promises instead of the question "how many rows exist".
    """
    resp = await client.get(f"/api/deals/{seed_deal.id}", headers=sender_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(seed_deal.id)


async def test_get_deal_forbidden_for_outsider(client, carrier_headers, sender_headers):
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await make_account({
            "email": f"outsider-{deal_id[:8]}@vimana.test",
            "password": "outsider-pass",
            "display_name": "Outsider",
        },
    )
    assert resp.status_code == 201
    login = await client.post(
        "/api/auth/login",
        json={"login": resp.json()["email"], "password": "outsider-pass"},
    )
    outsider_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/deals/{deal_id}", headers=outsider_headers)
    assert resp.status_code == 403


# ── T3.11.26 · the list has to be choosable from ─────────────────────────────


async def test_list_deals_names_the_counterparty_and_the_route(
    client, sender_headers, carrier_headers
):
    """Names and route travel with the list, not only with the detail.

    The deals page groups by the person a deal is with, and a column of
    truncated UUIDs is a list nobody can choose from. Fetching them per row
    would be four requests × twenty rows for something the server already has
    open in front of it, so `list_deals` batches two lookups for the page.
    """
    trip_id = await _create_open_trip(client, carrier_headers)
    deal_id = await _match_deal(client, sender_headers, trip_id)

    resp = await client.get("/api/deals", headers=sender_headers, params={"limit": 100})
    assert resp.status_code == 200, resp.text
    mine = next(d for d in resp.json()["items"] if d["id"] == deal_id)

    assert mine["sender_name"], mine
    assert mine["carrier_name"], mine
    # The route comes off the trip, which is what makes one row tell itself
    # apart from another in the same person's group.
    assert mine["origin"] and mine["destination"], mine


async def test_list_deals_route_is_all_or_nothing(client, sender_headers):
    """A row has both ends of the route or neither.

    The enrichment is a batched lookup, not a join, so a trip it cannot resolve
    has to degrade to `None` on **both** columns — half a route is the shape
    that prints «DXB → undefined» on the card.
    """
    resp = await client.get("/api/deals", headers=sender_headers, params={"limit": 20})
    assert resp.status_code == 200, resp.text
    for row in resp.json()["items"]:
        assert (row["origin"] is None) == (row["destination"] is None), row


# ── T3.11.07 · the order asks only for what the trip published ────────────


async def test_order_cannot_ask_for_a_category_the_trip_does_not_carry(
    client, carrier_headers, sender_headers
):
    """Owner's rule 2026-09-08: «перевозчик выставляет свои возможности,
    отправитель выбирает из того что может сделать перевозчик».

    Until this check existed the match path took any category at all and created
    it, so a deal for animals could be attached to a carrier who never said they
    take animals — and the carrier found out when the parcel arrived with a cat
    in it.
    """
    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "legs": [
                {
                    "origin": "AAA",
                    "destination": "BBB",
                    "depart_at": (
                        datetime.now(timezone.utc) + timedelta(days=3)
                    ).isoformat(),
                }
            ],
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201, trip.text

    r = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000000001",
                "origin": "AAA",
                "destination": "BBB",
                "category": "animals",
                "declared_value": 100.0,
            },
        },
    )
    assert r.status_code == 409, r.text


async def test_a_trip_that_named_no_categories_still_takes_a_deal(
    client, carrier_headers, sender_headers
):
    """Silence is not an offer of nothing.

    `allowed_categories` is optional so that a route and a date publish a trip —
    31 % of this market publishes within two days of the flight. Reading an empty
    list as «carries nothing» would make every express listing unbookable.
    """
    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "legs": [
                {
                    "origin": "CCC",
                    "destination": "DDD",
                    "depart_at": (
                        datetime.now(timezone.utc) + timedelta(days=3)
                    ).isoformat(),
                }
            ],
        },
    )
    assert trip.status_code == 201, trip.text

    r = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000000002",
                "origin": "CCC",
                "destination": "DDD",
                "category": "document",
                "declared_value": 100.0,
            },
        },
    )
    assert r.status_code == 201, r.text
