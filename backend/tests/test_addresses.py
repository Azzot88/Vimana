"""T_UX.4 A — CRUD for multiple receiving addresses per user."""
from __future__ import annotations

import uuid

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _register_and_login(client) -> dict:
    email = unique_email("addr")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "A"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_list_empty_for_new_user(client):
    hdr = await _register_and_login(client)
    r = await client.get("/api/me/addresses", headers=hdr)
    assert r.status_code == 200
    assert r.json() == []


async def test_create_first_address_auto_becomes_default(client):
    hdr = await _register_and_login(client)
    r = await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU", "city": "Moscow"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["is_default"] is True


async def test_create_second_address_not_default(client):
    hdr = await _register_and_login(client)
    await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU"},
    )
    r = await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Office", "country_iso": "RU"},
    )
    assert r.status_code == 201
    assert r.json()["is_default"] is False


async def test_create_with_is_default_clears_previous_default(client):
    hdr = await _register_and_login(client)
    first = await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU"},
    )
    second = await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Office", "country_iso": "RU", "is_default": True},
    )
    assert first.json()["is_default"] is True
    assert second.json()["is_default"] is True
    listing = (await client.get("/api/me/addresses", headers=hdr)).json()
    defaults = [a for a in listing if a["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["label"] == "Office"


async def test_make_default_endpoint(client):
    hdr = await _register_and_login(client)
    a = (await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU"},
    )).json()
    b = (await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Office", "country_iso": "RU"},
    )).json()
    assert a["is_default"] and not b["is_default"]
    r = await client.post(f"/api/me/addresses/{b['id']}/default", headers=hdr)
    assert r.status_code == 200
    assert r.json()["is_default"] is True
    listing = (await client.get("/api/me/addresses", headers=hdr)).json()
    defaults = [x for x in listing if x["is_default"]]
    assert len(defaults) == 1 and defaults[0]["id"] == b["id"]


async def test_update_address(client):
    hdr = await _register_and_login(client)
    a = (await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU"},
    )).json()
    r = await client.patch(
        f"/api/me/addresses/{a['id']}",
        headers=hdr,
        json={"label": "Home renamed", "city": "Saint-Petersburg"},
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Home renamed"
    assert r.json()["city"] == "Saint-Petersburg"


async def test_delete_promotes_another_to_default(client):
    hdr = await _register_and_login(client)
    a = (await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU"},
    )).json()
    b = (await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Office", "country_iso": "RU"},
    )).json()
    r = await client.delete(f"/api/me/addresses/{a['id']}", headers=hdr)
    assert r.status_code == 204
    remaining = (await client.get("/api/me/addresses", headers=hdr)).json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == b["id"]
    assert remaining[0]["is_default"] is True


async def test_delete_last_address(client):
    hdr = await _register_and_login(client)
    a = (await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "RU"},
    )).json()
    r = await client.delete(f"/api/me/addresses/{a['id']}", headers=hdr)
    assert r.status_code == 204
    assert (await client.get("/api/me/addresses", headers=hdr)).json() == []


async def test_cannot_touch_other_users_address(client):
    hdr_a = await _register_and_login(client)
    hdr_b = await _register_and_login(client)
    a = (await client.post(
        "/api/me/addresses",
        headers=hdr_a,
        json={"label": "Home", "country_iso": "RU"},
    )).json()
    # B tries to update A's address
    r = await client.patch(
        f"/api/me/addresses/{a['id']}", headers=hdr_b, json={"label": "hijack"}
    )
    assert r.status_code == 404
    # B tries to delete
    r2 = await client.delete(f"/api/me/addresses/{a['id']}", headers=hdr_b)
    assert r2.status_code == 404


async def test_country_iso_normalized_uppercase(client):
    hdr = await _register_and_login(client)
    r = await client.post(
        "/api/me/addresses",
        headers=hdr,
        json={"label": "Home", "country_iso": "ru"},
    )
    assert r.status_code == 201
    assert r.json()["country_iso"] == "RU"
