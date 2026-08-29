"""T1.23 — arbiter role, User Zero, invite-only DealVault access."""
import uuid as uuidlib
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.user import User
from tests.conftest import make_account


@pytest_asyncio.fixture
async def superuser_headers(client, session_maker, seed_carrier):
    """Promote seed_carrier to superuser for the scope of these tests."""
    async with session_maker() as db:
        u = await db.get(User, seed_carrier.id)
        u.roles = ["superuser"]
        await db.commit()
    try:
        from tests.conftest import _login
        token = await _login(client, seed_carrier.email)
        yield {"Authorization": f"Bearer {token}"}
    finally:
        async with session_maker() as db:
            u = await db.get(User, seed_carrier.id)
            u.roles = []
            await db.commit()


@pytest_asyncio.fixture
async def arbiter_user(client, session_maker):
    """Register a fresh arbiter — not a participant of the seed deal."""
    from tests.conftest import SEED_PASSWORD, _login, unique_email
    email = unique_email("arbiter")
    reg = await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Arbiter"},
    )
    assert reg.status_code == 201
    user_id = uuidlib.UUID(reg.json()["id"])

    async with session_maker() as db:
        u = await db.get(User, user_id)
        u.roles = ["arbiter"]
        await db.commit()

    token = await _login(client, email)
    return {"id": user_id, "email": email, "headers": {"Authorization": f"Bearer {token}"}}


async def _make_active_deal(client, carrier_headers, sender_headers) -> str:
    resp = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "DIS",
            "destination": "PUT",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = resp.json()["id"]
    match = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000000010",
                "origin": "DIS",
                "destination": "PUT",
                "category": "document",
                "declared_value": 100.0,
            },
        },
    )
    return match.json()["id"]


async def test_dispute_open_by_participant(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    resp = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "Carrier stopped responding after handoff"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "open"


async def test_dispute_open_by_outsider_forbidden(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    from tests.conftest import SEED_PASSWORD, _login, unique_email
    email = unique_email("outsider")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "O"},
    )
    token = await _login(client, email)
    outsider = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=outsider,
        json={"reason": "not mine"},
    )
    assert resp.status_code == 403


async def test_dispute_duplicate_returns_409(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    first = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "first"},
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "second"},
    )
    assert second.status_code == 409


async def test_arbiter_cannot_read_vault_without_claim(client, carrier_headers, sender_headers, arbiter_user):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    resp = await client.get(
        f"/api/admin/deals/{deal_id}/vault", headers=arbiter_user["headers"]
    )
    assert resp.status_code == 403


async def test_arbiter_reads_vault_after_claim_writes_audit(
    client, carrier_headers, sender_headers, arbiter_user
):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    # Sender opens dispute
    dispute_resp = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "Need help"},
    )
    dispute_id = dispute_resp.json()["id"]

    # Arbiter claims it
    claim = await client.post(
        f"/api/disputes/{dispute_id}/claim", headers=arbiter_user["headers"]
    )
    assert claim.status_code == 200

    # Arbiter reads DealVault — should succeed + write audit + system-message
    read = await client.get(
        f"/api/admin/deals/{deal_id}/vault", headers=arbiter_user["headers"]
    )
    assert read.status_code == 200

    # Participants see the system-message
    participant_view = await client.get(
        f"/api/deals/{deal_id}/dealvault", headers=sender_headers
    )
    body = participant_view.json()
    system_msgs = [m for m in body["items"] if m["is_system"]]
    assert any("Arbiter opened" in (m.get("text") or "") for m in system_msgs)


async def test_arbiter_cannot_claim_own_deal(client, carrier_headers, sender_headers, session_maker):
    """A user who is arbiter AND participant cannot claim their own deal's dispute."""
    from tests.conftest import _login

    # Get sender user_id via /me and promote them to arbiter
    me = await client.get("/api/auth/me", headers=sender_headers)
    sender_id = uuidlib.UUID(me.json()["id"])
    async with session_maker() as db:
        u = await db.get(User, sender_id)
        u.roles = ["arbiter"]
        await db.commit()

    try:
        deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
        dispute_resp = await client.post(
            f"/api/deals/{deal_id}/dispute",
            headers=sender_headers,
            json={"reason": "self-dispute"},
        )
        dispute_id = dispute_resp.json()["id"]
        claim = await client.post(
            f"/api/disputes/{dispute_id}/claim", headers=sender_headers
        )
        assert claim.status_code == 403
    finally:
        async with session_maker() as db:
            u = await db.get(User, sender_id)
            u.roles = []
            await db.commit()


async def test_admin_users_requires_superuser(client, arbiter_user):
    resp = await client.get("/api/admin/users", headers=arbiter_user["headers"])
    assert resp.status_code == 403


async def test_admin_users_lists_all_for_superuser(client, superuser_headers):
    resp = await client.get("/api/admin/users", headers=superuser_headers)
    assert resp.status_code == 200
    assert "items" in resp.json()


async def test_offering_a_role_is_superuser_only(client, superuser_headers, sender_headers):
    """T3.42 replaced `promote-arbiter` with an offer.

    The shape of the check is the same as before — a non-superuser must not get
    near it — but the outcome is not: an offer grants nothing, so the assertion
    that used to read `role == "arbiter"` now reads `roles == []`, and stays
    that way until somebody accepts. Acceptance itself is exercised in
    `test_role_offers.py`; the seed account is left untouched here on purpose,
    because `e2e/specs/admin-guard.spec.ts` depends on its role.
    """
    me_r = await client.get("/api/auth/me", headers=sender_headers)
    target_id = me_r.json()["id"]

    forbidden = await client.post(
        f"/api/admin/users/{target_id}/roles",
        headers=sender_headers,
        json={"role": "arbiter"},
    )
    assert forbidden.status_code == 403

    offered = await client.post(
        f"/api/admin/users/{target_id}/roles",
        headers=superuser_headers,
        json={"role": "arbiter", "reason": "test"},
    )
    assert offered.status_code == 201
    assert offered.json()["event"] == "offered"

    # The offer did not move the account.
    still = await client.get("/api/auth/me", headers=sender_headers)
    assert still.json()["roles"] == []

    # Take it back, so the seed account ends the test as it started.
    revoked = await client.request(
        "DELETE",
        f"/api/admin/users/{target_id}/roles/arbiter",
        headers=superuser_headers,
        json={"reason": "test cleanup"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["event"] == "revoked"
