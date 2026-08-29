"""T_TEST.3 — admin users list filter + delete + Celery e2e cleanup task."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from tests.conftest import make_account


async def _register(client, email: str, *, carrier: bool = False):
    from tests.conftest import SEED_PASSWORD

    payload = {"email": email, "password": SEED_PASSWORD, "display_name": email[:8]}
    if carrier:
        payload.update({"can_carry": True, "active_mode": "carrier"})
    await make_account(payload)
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _promote_to_superuser(session_maker, email: str):
    from sqlalchemy import select

    from app.models.user import User

    async with session_maker() as db:
        u = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        u.roles = ["superuser"]
        await db.commit()


async def test_list_users_filter_by_email_contains(client, session_maker):
    from tests.conftest import unique_email

    admin_email = unique_email("adm")
    hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    e2e_email = f"e2e-x-{unique_email('r').split('@')[0]}@e2e.vimana.local"
    await _register(client, e2e_email)

    r = await client.get(
        "/api/admin/users",
        headers=hdr,
        params={"email_contains": "@e2e.vimana.local", "limit": 100},
    )
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()["items"]]
    assert e2e_email in emails
    assert all("@e2e.vimana.local" in (e or "") for e in emails)


async def test_delete_user_cascade_removes_related_rows(client, session_maker):
    """Superuser DELETE cleans user + their trips + deals + messages."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.deal import Deal, DealVaultMessage
    from app.models.marketplace import Trip
    from app.models.user import User
    from tests.conftest import unique_email

    admin_email = unique_email("adm2")
    admin_hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    victim_email = f"e2e-del-{unique_email('r').split('@')[0]}@e2e.vimana.local"
    v_hdr = await _register(client, victim_email, carrier=True)

    # Victim publishes a trip.
    trip = await client.post(
        "/api/trips",
        headers=v_hdr,
        json={
            "origin": "DEL",
            "destination": "GON",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201
    trip_id = trip.json()["id"]

    async with session_maker() as db:
        v_user = (
            await db.execute(select(User).where(User.email == victim_email))
        ).scalar_one()
        v_id = v_user.id

    r = await client.delete(f"/api/admin/users/{v_id}", headers=admin_hdr)
    assert r.status_code == 204

    async with session_maker() as db:
        assert (await db.get(User, v_id)) is None
        assert (await db.get(Trip, trip_id)) is None


async def test_delete_user_forbidden_for_non_superuser(client, session_maker):
    from tests.conftest import unique_email

    hdr = await _register(client, unique_email("nope"))
    other_hdr = await _register(client, unique_email("victim"))
    # First user is NOT superuser → 403.
    from sqlalchemy import select

    from app.models.user import User

    async with session_maker() as db:
        victim = (
            await db.execute(
                select(User).where(User.email.like("victim%"))
            )
        ).scalars().first()
    r = await client.delete(f"/api/admin/users/{victim.id}", headers=hdr)
    assert r.status_code == 403


async def test_delete_user_cannot_delete_superuser_or_self(client, session_maker):
    from tests.conftest import unique_email

    from sqlalchemy import select

    from app.models.user import User

    admin_email = unique_email("adm3")
    admin_hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    async with session_maker() as db:
        admin = (
            await db.execute(select(User).where(User.email == admin_email))
        ).scalar_one()

    r = await client.delete(f"/api/admin/users/{admin.id}", headers=admin_hdr)
    assert r.status_code == 400
    assert "yourself" in r.json()["detail"].lower()


def test_cleanup_e2e_users_task_deletes_stale(sync_sessions):
    """Direct sync-call to the Celery task function — simulate stale user.

    `sync_sessions` (autouse, conftest) binds the task to the TEST database.
    Without it this test seeds and prunes **production**: the task deletes users
    and cascades through their deals, messages and trust edges. On 2026-07-26 an
    unpatched run removed 22 real accounts from prod.
    """
    import uuid
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select, text as sa_text

    from app.core.security import hash_password
    from app.models.user import User
    from app.tasks.cleanup import E2E_MAX_AGE_HOURS, cleanup_e2e_users

    SyncSessionLocal = sync_sessions

    old_ts = datetime.now(tz=timezone.utc) - timedelta(hours=E2E_MAX_AGE_HOURS + 1)
    stale_email = f"e2e-old-{uuid.uuid4().hex[:6]}@e2e.vimana.local"
    fresh_email = f"e2e-fresh-{uuid.uuid4().hex[:6]}@e2e.vimana.local"

    with SyncSessionLocal() as db:
        stale = User(
            email=stale_email,
            password_hash=hash_password("x"),
            display_name="stale",
        )
        db.add(stale)
        db.commit()
        db.execute(
            sa_text("UPDATE users SET created_at = :t WHERE email = :e"),
            {"t": old_ts, "e": stale_email},
        )
        fresh = User(
            email=fresh_email,
            password_hash=hash_password("x"),
            display_name="fresh",
        )
        db.add(fresh)
        db.commit()

    result = cleanup_e2e_users()
    assert result["deleted"] >= 1

    with SyncSessionLocal() as db:
        assert (
            db.execute(select(User).where(User.email == stale_email))
            .scalar_one_or_none()
            is None
        ), "stale e2e user should be pruned"
        assert (
            db.execute(select(User).where(User.email == fresh_email))
            .scalar_one_or_none()
            is not None
        ), "fresh e2e user should survive (<24 h)"
