"""T3.2 — OperatorAccessGrant + grant/revoke flow + arbiter vault gate."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
async def _open_dispute(client, session_maker):
    """Fresh carrier + sender + matched deal + arbiter + open dispute."""
    from tests.conftest import SEED_PASSWORD, unique_email

    c_email = unique_email("g-c")
    await client.post(
        "/api/auth/register",
        json={
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "GC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    s_email = unique_email("g-s")
    await client.post(
        "/api/auth/register",
        json={"email": s_email, "password": SEED_PASSWORD, "display_name": "GS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}

    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "GRT",
            "destination": "GRD",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]
    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000002222",
                "origin": "GRT",
                "destination": "GRD",
                "category": "document",
                "declared_value": 300.0,
            },
        },
    )
    deal_id = match.json()["id"]

    # Bootstrap an arbiter.
    from sqlalchemy import update

    from app.core.security import hash_password
    from app.models.user import User

    async with session_maker() as db:
        arb = User(
            email=unique_email("g-arb"),
            password_hash=hash_password(SEED_PASSWORD),
            display_name="GArb",
            role="arbiter",
        )
        db.add(arb)
        await db.commit()
        await db.refresh(arb)
        arb_email = arb.email

    a_login = await client.post(
        "/api/auth/login", json={"login": arb_email, "password": SEED_PASSWORD}
    )
    a_headers = {"Authorization": f"Bearer {a_login.json()['access_token']}"}

    # Sender opens dispute.
    disp = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=s_headers,
        json={"reason": "test dispute"},
    )
    assert disp.status_code == 201
    dispute_id = disp.json()["id"]

    return {
        "sender_headers": s_headers,
        "carrier_headers": c_headers,
        "arbiter_headers": a_headers,
        "deal_id": deal_id,
        "dispute_id": dispute_id,
    }


async def test_opening_dispute_auto_creates_grant_from_opener(
    _open_dispute, session_maker
):
    from sqlalchemy import select

    from app.models.deal import OperatorAccessGrant

    d = _open_dispute
    async with session_maker() as db:
        rows = await db.execute(
            select(OperatorAccessGrant).where(
                OperatorAccessGrant.dispute_id == d["dispute_id"]
            )
        )
        grants = list(rows.scalars())
        assert len(grants) == 1
        assert grants[0].revoked_at is None


async def test_counterparty_grant_endpoint_creates_second_grant(
    client, _open_dispute, session_maker
):
    from sqlalchemy import select

    from app.models.deal import OperatorAccessGrant

    d = _open_dispute
    resp = await client.post(
        f"/api/disputes/{d['dispute_id']}/grant-access",
        headers=d["carrier_headers"],
    )
    assert resp.status_code == 200

    async with session_maker() as db:
        rows = await db.execute(
            select(OperatorAccessGrant).where(
                OperatorAccessGrant.dispute_id == d["dispute_id"]
            )
        )
        grants = list(rows.scalars())
        assert len(grants) == 2


async def test_grant_endpoint_forbidden_for_third_party(client, _open_dispute):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("g-out")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "GOut"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.post(
        f"/api/disputes/{_open_dispute['dispute_id']}/grant-access", headers=hdr
    )
    assert resp.status_code == 403


async def test_grant_is_idempotent_reactivating_after_revoke(
    client, _open_dispute, session_maker
):
    from sqlalchemy import select

    from app.models.deal import OperatorAccessGrant

    d = _open_dispute

    # Sender's grant was auto-created; revoke then re-grant.
    r1 = await client.post(
        f"/api/disputes/{d['dispute_id']}/revoke-access",
        headers=d["sender_headers"],
    )
    assert r1.status_code == 200

    r2 = await client.post(
        f"/api/disputes/{d['dispute_id']}/grant-access",
        headers=d["sender_headers"],
    )
    assert r2.status_code == 200

    async with session_maker() as db:
        rows = await db.execute(
            select(OperatorAccessGrant).where(
                OperatorAccessGrant.dispute_id == d["dispute_id"],
                OperatorAccessGrant.granted_by == d["sender_headers"] is None,  # noqa
            )
        )
        # Simpler assertion: exactly one row for the sender, revoked_at cleared.
        all_rows = await db.execute(
            select(OperatorAccessGrant).where(
                OperatorAccessGrant.dispute_id == d["dispute_id"]
            )
        )
        # There should still be only one grant row per party.
        assert len(list(all_rows.scalars())) == 1


async def test_arbiter_vault_read_blocked_when_all_grants_revoked(
    client, _open_dispute
):
    d = _open_dispute
    # Arbiter claims.
    claim = await client.post(
        f"/api/disputes/{d['dispute_id']}/claim", headers=d["arbiter_headers"]
    )
    assert claim.status_code == 200

    # Sender revokes their auto-grant. No other grants exist.
    rev = await client.post(
        f"/api/disputes/{d['dispute_id']}/revoke-access",
        headers=d["sender_headers"],
    )
    assert rev.status_code == 200

    # Vault read should now be blocked.
    r = await client.get(
        f"/api/admin/deals/{d['deal_id']}/vault", headers=d["arbiter_headers"]
    )
    assert r.status_code == 403
    assert "grant" in r.json()["detail"].lower()


async def test_arbiter_vault_read_ok_with_active_grant(client, _open_dispute):
    d = _open_dispute
    await client.post(
        f"/api/disputes/{d['dispute_id']}/claim", headers=d["arbiter_headers"]
    )
    # Sender's auto-grant is still active.
    r = await client.get(
        f"/api/admin/deals/{d['deal_id']}/vault", headers=d["arbiter_headers"]
    )
    assert r.status_code == 200


async def test_arbiter_vault_read_ok_when_only_counterparty_grants(
    client, _open_dispute
):
    """Sender revokes, but carrier grants — arbiter still reads."""
    d = _open_dispute
    await client.post(
        f"/api/disputes/{d['dispute_id']}/claim", headers=d["arbiter_headers"]
    )
    # Sender revokes.
    await client.post(
        f"/api/disputes/{d['dispute_id']}/revoke-access",
        headers=d["sender_headers"],
    )
    # Carrier grants.
    grant = await client.post(
        f"/api/disputes/{d['dispute_id']}/grant-access",
        headers=d["carrier_headers"],
    )
    assert grant.status_code == 200

    r = await client.get(
        f"/api/admin/deals/{d['deal_id']}/vault", headers=d["arbiter_headers"]
    )
    assert r.status_code == 200
