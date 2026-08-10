"""Race condition regression tests for T1.19 (block 1)."""
import asyncio
import uuid as uuidlib
from datetime import datetime, timedelta, timezone
from tests.conftest import make_account


async def _make_trip(client, carrier_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "RCE",
            "destination": "DXB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _match(client, sender_headers, trip_id, category):
    return await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000099",
                "origin": "RCE",
                "destination": "DXB",
                "category": category,
                "declared_value": 25.0,
            },
        },
    )


async def test_concurrent_new_category_no_duplicate(client, carrier_headers, sender_headers):
    custom = f"race-{uuidlib.uuid4().hex[:8]}"
    trips = await asyncio.gather(*[_make_trip(client, carrier_headers) for _ in range(3)])
    results = await asyncio.gather(*[_match(client, sender_headers, t, custom) for t in trips])
    assert all(r.status_code == 201 for r in results), [r.text for r in results]

    resp = await client.get("/api/categories", params={"q": custom})
    entries = [c for c in resp.json() if c["name_key"] == custom]
    assert len(entries) == 1
    assert entries[0]["usage_count"] >= 3


async def test_waitlist_concurrent_duplicate_returns_409(client):
    email = f"race-wl-{uuidlib.uuid4().hex[:8]}@vimana.test"
    results = await asyncio.gather(
        *[client.post("/api/waitlist", json={"email": email}) for _ in range(5)],
        return_exceptions=True,
    )
    codes = [r.status_code for r in results if hasattr(r, "status_code")]
    assert codes.count(201) == 1
    assert codes.count(409) == 4


async def test_invite_concurrent_accept_only_one_wins(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    async def _register_and_accept(idx):
        email = f"race-inv-{idx}-{uuidlib.uuid4().hex[:6]}@vimana.test"
        pw = "race-pw-1"
        reg = await make_account({"email": email, "password": pw, "display_name": f"Race {idx}"},
        )
        assert reg.status_code == 201
        login = await client.post(
            "/api/auth/login", json={"login": email, "password": pw}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        return await client.post(f"/api/invites/{token}/accept", headers=headers)

    results = await asyncio.gather(*[_register_and_accept(i) for i in range(4)])
    codes = [r.status_code for r in results]
    assert codes.count(200) == 1
    assert codes.count(409) == 3
