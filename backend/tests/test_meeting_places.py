"""T3.11.07 — meeting places: a list in the profile, one of them default.

Not addresses. An address is where a parcel is sent and carries the structure
the post office needs; a meeting place is «у метро Фили, у выхода №3» — a
sentence one person says to another. The list mechanics are the same as for
addresses, and that is exactly why they are worth testing separately: the same
rule implemented twice is the rule that drifts.
"""
from __future__ import annotations

import uuid

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _create(client, headers, description: str, is_default: bool = False):
    return await client.post(
        "/api/me/meeting-places",
        headers=headers,
        json={"description": description, "is_default": is_default},
    )


async def _fresh_headers(client) -> dict[str, str]:
    """A person who owns nothing yet.

    Needed because `vimana_test` is never reset (ENVIRONMENT §8): the shared
    carrier accumulates rows from every test above, so "the first one" is only
    the first for somebody who has just arrived. Asserting a first-time rule
    against a shared account is how a test passes on a clean database and fails
    on the second run — which is exactly how this one failed.
    """
    email = unique_email("places")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Places"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_first_place_becomes_the_default(client):
    """A list with entries and no default makes every form that offers one
    start empty, so the first row is promoted on the way in."""
    headers = await _fresh_headers(client)
    r = await _create(client, headers, "У метро Фили, выход №3")
    assert r.status_code == 201, r.text
    assert r.json()["is_default"] is True

    # And only the first: the second is an ordinary row.
    second = await _create(client, headers, "Terminal D, departures")
    assert second.json()["is_default"] is False


async def test_a_second_default_unseats_the_first(client, carrier_headers):
    headers = carrier_headers
    first = (await _create(client, headers, "Terminal D, departures")).json()
    second = (
        await _create(client, headers, "Кофейня у выхода", is_default=True)
    ).json()

    listing = (await client.get("/api/me/meeting-places", headers=headers)).json()
    by_id = {p["id"]: p for p in listing}
    assert by_id[second["id"]]["is_default"] is True
    assert by_id[first["id"]]["is_default"] is False


async def test_default_is_listed_first(client, carrier_headers):
    """The form offers the top of this list, so the order is the answer."""
    await _create(client, carrier_headers, "Первое место")
    chosen = (
        await _create(client, carrier_headers, "Второе место", is_default=True)
    ).json()
    listing = (
        await client.get("/api/me/meeting-places", headers=carrier_headers)
    ).json()
    assert listing[0]["id"] == chosen["id"]


async def test_deleting_the_default_promotes_another(client, carrier_headers):
    """A list with entries and no default makes every form that offers one start
    empty, so the successor is promoted.

    Asserted as "exactly one default remains" rather than "this specific row
    became it": the test database is never reset (ENVIRONMENT §8), so this
    carrier already owns places from the tests above, and the successor is the
    oldest of all of them rather than the one created two lines up. The rule
    being tested is that a default exists, not which row it landed on.
    """
    headers = carrier_headers
    await _create(client, headers, "Остаётся")
    doomed = (await _create(client, headers, "Удаляется", is_default=True)).json()

    gone = await client.delete(
        f"/api/me/meeting-places/{doomed['id']}", headers=headers
    )
    assert gone.status_code == 204

    listing = (await client.get("/api/me/meeting-places", headers=headers)).json()
    defaults = [p for p in listing if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] != doomed["id"]


async def test_description_is_trimmed(client, carrier_headers):
    r = await _create(client, carrier_headers, "   У фонтана   ")
    assert r.json()["description"] == "У фонтана"


async def test_empty_description_is_refused(client, carrier_headers):
    """The whole point of the row is the sentence in it."""
    r = await _create(client, carrier_headers, "")
    assert r.status_code == 422


async def test_somebody_elses_place_is_not_found(client, carrier_headers, sender_headers):
    """404 rather than 403: telling a stranger "this id is real but not yours"
    answers a question they had no business asking."""
    mine = (await _create(client, carrier_headers, "Моё место")).json()

    seen = await client.get(
        "/api/me/meeting-places", headers=sender_headers
    )
    assert all(p["id"] != mine["id"] for p in seen.json())

    for call in (
        client.patch(
            f"/api/me/meeting-places/{mine['id']}",
            headers=sender_headers,
            json={"description": "Подменённое"},
        ),
        client.post(
            f"/api/me/meeting-places/{mine['id']}/default", headers=sender_headers
        ),
        client.delete(f"/api/me/meeting-places/{mine['id']}", headers=sender_headers),
    ):
        assert (await call).status_code == 404


async def test_unknown_place_is_not_found(client, carrier_headers):
    r = await client.delete(
        f"/api/me/meeting-places/{uuid.uuid4()}", headers=carrier_headers
    )
    assert r.status_code == 404


async def test_places_need_a_signed_in_person(client):
    r = await client.get("/api/me/meeting-places")
    assert r.status_code in (401, 403)
