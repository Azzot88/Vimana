"""T1.24 — dual role, capabilities, and active_mode switching."""
from datetime import datetime, timedelta, timezone

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def _register(client, email: str, *, can_carry=True, can_send=True, active_mode="sender"):
    resp = await make_account({
            "email": email,
            "password": SEED_PASSWORD,
            "display_name": "Dual",
            "can_carry": can_carry,
            "can_send": can_send,
            "active_mode": active_mode,
        },
    )
    assert resp.status_code == 201, resp.text
    login = await client.post(
        "/api/auth/login",
        json={"login": email, "password": SEED_PASSWORD},
    )
    return {
        "id": resp.json()["id"],
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


async def test_user_out_exposes_capabilities_no_is_carrier(client):
    user = await _register(client, unique_email("caps"))
    me = await client.get("/api/auth/me", headers=user["headers"])
    body = me.json()
    assert "is_carrier" not in body
    assert body["can_carry"] is True
    assert body["can_send"] is True
    assert body["active_mode"] == "sender"


async def test_default_registration_makes_both_capabilities_true(client):
    resp = await make_account({
            "email": unique_email("dflt"),
            "password": SEED_PASSWORD,
            "display_name": "Default",
        },
    )
    body = resp.json()
    assert body["can_carry"] is True
    assert body["can_send"] is True
    assert body["active_mode"] == "sender"


async def test_patch_active_mode_switch_to_carrier(client):
    user = await _register(client, unique_email("switch"))
    resp = await client.patch(
        "/api/auth/me",
        headers=user["headers"],
        json={"active_mode": "carrier"},
    )
    assert resp.status_code == 200
    assert resp.json()["active_mode"] == "carrier"


async def test_patch_active_mode_rejects_invalid(client):
    user = await _register(client, unique_email("bad"))
    resp = await client.patch(
        "/api/auth/me",
        headers=user["headers"],
        json={"active_mode": "banana"},
    )
    assert resp.status_code == 422


async def test_post_trip_requires_can_carry(client):
    """Even in sender mode, having can_carry=True is enough to publish."""
    user = await _register(client, unique_email("carry"), can_carry=True)
    resp = await client.post(
        "/api/trips",
        headers=user["headers"],
        json={
            "origin": "AAA",
            "destination": "BBB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
        },
    )
    assert resp.status_code == 201


async def test_post_trip_forbidden_when_can_carry_false(client):
    user = await _register(client, unique_email("nocarry"), can_carry=False)
    resp = await client.post(
        "/api/trips",
        headers=user["headers"],
        json={
            "origin": "AAA",
            "destination": "BBB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
        },
    )
    assert resp.status_code == 403


async def test_patch_can_carry_flag(client):
    user = await _register(client, unique_email("togcarry"))
    resp = await client.patch(
        "/api/auth/me",
        headers=user["headers"],
        json={"can_carry": False},
    )
    assert resp.status_code == 200
    assert resp.json()["can_carry"] is False
