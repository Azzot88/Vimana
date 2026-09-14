"""T3.12.03 pt.2 — cargo templates.

`D-CARGO-MODEL`: a template is filled in at the response and kept in the
cabinet, and it reaches a cargo **as a snapshot**. What is pinned is that
property — a template edited after the response does not reach the cargo, and a
response the server refuses leaves no template behind — plus the ownership of
the list. A stranger's PATCH and DELETE are also rows of `test_idor_matrix.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _login(client) -> dict:
    email = unique_email("tmpl")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "T"})
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _open_trip(client, carrier_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "segments": [
                {
                    "origin": "TPL",
                    "destination": "TPD",
                    "depart_at": (
                        datetime.now(timezone.utc) + timedelta(days=5)
                    ).isoformat(),
                }
            ],
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _mine(client, headers) -> list[dict]:
    resp = await client.get("/api/me/cargo-templates", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── the list ──────────────────────────────────────────────────────────────


async def test_a_new_account_has_no_templates(client):
    assert await _mine(client, await _login(client)) == []


async def test_templates_are_kept_by_name(client):
    hdr = await _login(client)
    for name in ("Medicine to Almaty", "Documents to Lisbon"):
        created = await client.post(
            "/api/me/cargo-templates",
            headers=hdr,
            json={
                "name": f"  {name}  ",
                "category": " Document ",
                "declared_value": 120.0,
                "description": "a folder",
            },
        )
        assert created.status_code == 201, created.text

    listed = await _mine(client, hdr)
    assert [t["name"] for t in listed] == ["Documents to Lisbon", "Medicine to Almaty"]
    # Stored the way the response stores a category, so a template offered to
    # the response form names one the trip can be checked against.
    assert {t["category"] for t in listed} == {"document"}


async def test_a_name_of_spaces_is_no_name(client):
    hdr = await _login(client)
    resp = await client.post(
        "/api/me/cargo-templates", headers=hdr, json={"name": "   "}
    )
    assert resp.status_code == 422
    assert await _mine(client, hdr) == []


async def test_editing_changes_only_what_was_sent(client):
    hdr = await _login(client)
    created = (
        await client.post(
            "/api/me/cargo-templates",
            headers=hdr,
            json={"name": "Keys", "category": "document", "declared_value": 10.0},
        )
    ).json()

    patched = await client.patch(
        f"/api/me/cargo-templates/{created['id']}",
        headers=hdr,
        json={"description": "a spare set"},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["description"] == "a spare set"
    assert body["name"] == "Keys"
    assert body["declared_value"] == 10.0

    cleared = await client.patch(
        f"/api/me/cargo-templates/{created['id']}", headers=hdr, json={"name": None}
    )
    assert cleared.status_code == 422


async def test_a_stranger_neither_sees_nor_touches_a_template(client):
    owner = await _login(client)
    stranger = await _login(client)
    created = (
        await client.post(
            "/api/me/cargo-templates", headers=owner, json={"name": "Mine"}
        )
    ).json()

    assert await _mine(client, stranger) == []
    patched = await client.patch(
        f"/api/me/cargo-templates/{created['id']}",
        headers=stranger,
        json={"name": "Theirs"},
    )
    assert patched.status_code == 404
    deleted = await client.delete(
        f"/api/me/cargo-templates/{created['id']}", headers=stranger
    )
    assert deleted.status_code == 404
    assert [t["name"] for t in await _mine(client, owner)] == ["Mine"]


async def test_a_deleted_template_is_gone(client):
    hdr = await _login(client)
    created = (
        await client.post("/api/me/cargo-templates", headers=hdr, json={"name": "Once"})
    ).json()
    resp = await client.delete(f"/api/me/cargo-templates/{created['id']}", headers=hdr)
    assert resp.status_code == 204
    assert await _mine(client, hdr) == []
    again = await client.delete(f"/api/me/cargo-templates/{created['id']}", headers=hdr)
    assert again.status_code == 404


# ── at the response ───────────────────────────────────────────────────────


async def test_a_response_can_keep_its_cargo_as_a_template(
    client, carrier_headers, sender_headers
):
    trip_id = await _open_trip(client, carrier_headers)
    name = f"Contract copy {uuid.uuid4().hex[:6]}"
    matched = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "cargo": {
                "weight_kg": 1.0,
                "category": "document",
                "declared_value": 75.0,
                "description": "signed copy",
            },
            "save_as_template": name,
        },
    )
    assert matched.status_code == 201, matched.text

    saved = [t for t in await _mine(client, sender_headers) if t["name"] == name]
    assert len(saved) == 1
    assert saved[0]["category"] == "document"
    assert saved[0]["declared_value"] == 75.0
    assert saved[0]["description"] == "signed copy"


async def test_editing_the_template_does_not_reach_the_cargo(
    client, carrier_headers, sender_headers, session_maker
):
    from app.models.marketplace import Cargo

    trip_id = await _open_trip(client, carrier_headers)
    name = f"Snapshot {uuid.uuid4().hex[:6]}"
    deal_id = (
        await client.post(
            "/api/deals/match",
            headers=sender_headers,
            json={
                "trip_id": trip_id,
                "cargo": {
                    "weight_kg": 1.0,
                    "category": "document",
                    "declared_value": 30.0,
                    "description": "as answered",
                },
                "save_as_template": name,
            },
        )
    ).json()["id"]
    template = next(t for t in await _mine(client, sender_headers) if t["name"] == name)

    await client.patch(
        f"/api/me/cargo-templates/{template['id']}",
        headers=sender_headers,
        json={"description": "edited later", "declared_value": 999.0},
    )
    await client.delete(
        f"/api/me/cargo-templates/{template['id']}", headers=sender_headers
    )

    cargo_id = (
        await client.get(f"/api/deals/{deal_id}", headers=sender_headers)
    ).json()["cargo_id"]
    async with session_maker() as db:
        cargo = await db.get(Cargo, uuid.UUID(cargo_id))
        assert cargo.description == "as answered"
        assert cargo.declared_value == 30.0


async def test_a_refused_response_keeps_no_template(
    client, carrier_headers, sender_headers
):
    trip_id = await _open_trip(client, carrier_headers)
    name = f"Refused {uuid.uuid4().hex[:6]}"
    refused = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            # The trip carries documents only.
            "cargo": {"weight_kg": 1.0, "category": "animals", "declared_value": 5.0},
            "save_as_template": name,
        },
    )
    assert refused.status_code == 409, refused.text
    assert not [t for t in await _mine(client, sender_headers) if t["name"] == name]
