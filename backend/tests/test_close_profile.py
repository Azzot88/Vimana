"""T3.12.06 pt.2 — close people see the whole profile, addresses included.

Owner, 2026-09-14. What is pinned is who sees what: a close person (an accepted
pair) sees the profile in full whatever it shows strangers, plus the addresses
and meeting places; a stranger, a mere contact and somebody whose request is
still unanswered see none of it.
"""
from __future__ import annotations

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _person(client, prefix: str):
    email = unique_email(prefix)
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": prefix.upper()})
    login = await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = (await client.get("/api/auth/me", headers=headers)).json()
    return headers, me["id"], me["nostr_pubkey"]


async def _with_address(client, headers):
    r = await client.post(
        "/api/me/addresses",
        headers=headers,
        json={"label": "Home", "country_iso": "PT", "city": "Lisbon", "street": "Rua Augusta 1"},
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/me/meeting-places",
        headers=headers,
        json={"description": "By the tram stop", "country_iso": "PT"},
    )
    assert r.status_code == 201, r.text


async def _make_close(client, a_headers, a_id, b_headers, b_id):
    await client.post("/api/me/connections", headers=a_headers, json={"user_id": b_id})
    asked = await client.post("/api/me/close", headers=a_headers, json={"user_id": b_id})
    assert asked.status_code == 201, asked.text
    accepted = await client.post(f"/api/me/close/{asked.json()['id']}/accept", headers=b_headers)
    assert accepted.status_code == 200, accepted.text


async def test_a_close_person_sees_the_addresses(client):
    owner_h, owner_id, owner_npub = await _person(client, "cp-owner")
    friend_h, friend_id, _ = await _person(client, "cp-friend")
    await _with_address(client, owner_h)
    await _make_close(client, friend_h, friend_id, owner_h, owner_id)

    seen = await client.get(f"/api/identities/{owner_npub}", headers=friend_h)
    assert seen.status_code == 200, seen.text
    close = seen.json()["close"]
    assert [a["street"] for a in close["addresses"]] == ["Rua Augusta 1"]
    assert [p["description"] for p in close["meeting_places"]] == ["By the tram stop"]
    # Contact details stay out even for close people.
    assert "email" not in seen.json() and "phone" not in seen.json()


async def test_nobody_else_sees_them(client):
    owner_h, owner_id, owner_npub = await _person(client, "cp-owner2")
    contact_h, contact_id, _ = await _person(client, "cp-contact")
    asker_h, asker_id, _ = await _person(client, "cp-asker")
    await _with_address(client, owner_h)

    # A contact, and somebody whose request is unanswered.
    await client.post("/api/me/connections", headers=contact_h, json={"user_id": owner_id})
    await client.post("/api/me/connections", headers=asker_h, json={"user_id": owner_id})
    await client.post("/api/me/close", headers=asker_h, json={"user_id": owner_id})

    for headers in (None, contact_h, asker_h):
        r = await client.get(f"/api/identities/{owner_npub}", headers=headers or {})
        assert r.status_code == 200, r.text
        assert r.json()["close"] is None


async def test_close_people_see_a_profile_hidden_from_everyone_else(client):
    owner_h, owner_id, owner_npub = await _person(client, "cp-hidden")
    friend_h, friend_id, _ = await _person(client, "cp-hidden-friend")
    stranger_h, _, _ = await _person(client, "cp-hidden-stranger")
    await _make_close(client, friend_h, friend_id, owner_h, owner_id)

    hidden = await client.patch("/api/auth/me", headers=owner_h, json={"public_profile": "hidden"})
    assert hidden.status_code == 200, hidden.text

    assert (await client.get(f"/api/identities/{owner_npub}", headers=stranger_h)).status_code == 404
    seen = await client.get(f"/api/identities/{owner_npub}", headers=friend_h)
    assert seen.status_code == 200, seen.text
    assert seen.json()["visibility"] == "full"

    # Ending closeness ends it.
    await client.delete(f"/api/me/close/{owner_id}", headers=friend_h)
    assert (await client.get(f"/api/identities/{owner_npub}", headers=friend_h)).status_code == 404


def test_the_gate_opens_to_close_people_but_not_to_a_closed_archive():
    from types import SimpleNamespace

    from app.core.permissions import visible_to

    hidden = SimpleNamespace(id="s", public_profile="hidden", archive_choice=None)
    archived = SimpleNamespace(id="s", public_profile="full", archive_choice="hide")
    viewer = SimpleNamespace(id="v", roles=["user"])
    assert visible_to(hidden, viewer) == "hidden"
    assert visible_to(hidden, viewer, close=True) == "full"
    assert visible_to(archived, viewer, close=True) == "hidden"
