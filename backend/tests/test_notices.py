"""T_UX.2 — public read endpoints for RouteNote + PlatformNotice."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


async def _add_route_note(session_maker, **overrides):
    from app.models.notices import (
        NoticeSeverity,
        RouteNote,
        RouteStatus,
    )

    async with session_maker() as db:
        n = RouteNote(
            id=uuid.uuid4(),
            origin_iso=overrides.get("origin_iso", "US"),
            destination_iso=overrides.get("destination_iso", "IR"),
            status=overrides.get("status", RouteStatus.complex),
            severity=overrides.get("severity", NoticeSeverity.warning),
            headline=overrides.get("headline", "US → IR"),
            body=overrides.get("body", "Sanctions apply."),
            active_from=overrides.get(
                "active_from", datetime.now(tz=timezone.utc) - timedelta(hours=1)
            ),
            active_until=overrides.get("active_until"),
        )
        db.add(n)
        await db.commit()
        return n.id


async def _add_platform_notice(session_maker, **overrides):
    from app.models.notices import NoticeSeverity, NoticeSurface, PlatformNotice

    async with session_maker() as db:
        n = PlatformNotice(
            id=uuid.uuid4(),
            key=overrides.get("key", f"notice.{uuid.uuid4().hex[:6]}"),
            severity=overrides.get("severity", NoticeSeverity.info),
            target_surface=overrides.get("target_surface", NoticeSurface.footer),
            headline=overrides.get("headline", "Platform disclaimer"),
            body=overrides.get("body", ""),
            active_from=overrides.get(
                "active_from", datetime.now(tz=timezone.utc) - timedelta(hours=1)
            ),
            active_until=overrides.get("active_until"),
        )
        db.add(n)
        await db.commit()
        return n.id


async def test_route_notes_returns_active_specific_match(client, session_maker):
    unique_headline = f"US → IR {uuid.uuid4().hex[:6]}"
    await _add_route_note(
        session_maker,
        origin_iso="US",
        destination_iso="IR",
        headline=unique_headline,
    )
    resp = await client.get("/api/route-notes?origin=US&destination=IR")
    assert resp.status_code == 200
    body = resp.json()
    assert any(n["headline"] == unique_headline for n in body)


async def test_route_notes_wildcard_matches_any_origin(client, session_maker):
    """Note with origin='*' must match a specific origin filter."""
    from app.models.notices import RouteStatus

    unique_dest = f"X{uuid.uuid4().hex[:2].upper()}"
    await _add_route_note(
        session_maker,
        origin_iso="*",
        destination_iso=unique_dest,
        status=RouteStatus.attention,
    )
    resp = await client.get(f"/api/route-notes?origin=FR&destination={unique_dest}")
    assert resp.status_code == 200
    matched = [n for n in resp.json() if n["destination_iso"] == unique_dest]
    assert len(matched) >= 1
    assert matched[0]["origin_iso"] == "*"


async def test_route_notes_expired_not_returned(client, session_maker):
    """Note with active_until in the past must be excluded."""
    unique_headline = f"expired-{uuid.uuid4().hex[:6]}"
    await _add_route_note(
        session_maker,
        origin_iso="DE",
        destination_iso="CU",
        headline=unique_headline,
        active_until=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    resp = await client.get("/api/route-notes?origin=DE&destination=CU")
    headlines = {n["headline"] for n in resp.json()}
    assert unique_headline not in headlines


async def test_route_notes_ranks_specific_before_wildcards(client, session_maker):
    """Overlap: `*→X` + `US→X` — both returned, specific first."""
    # Two hex chars is 256 possibilities against a table that accumulates across
    # runs — the same code eventually comes up twice and the assertion below
    # counts a previous run's notes. Match on the headlines this run created
    # instead; the destination code only has to be valid, not unique.
    dest = f"X{uuid.uuid4().hex[:2].upper()}"
    wild_headline = f"wild-{uuid.uuid4().hex[:6]}"
    specific_headline = f"specific-{uuid.uuid4().hex[:6]}"
    await _add_route_note(
        session_maker,
        origin_iso="*",
        destination_iso=dest,
        headline=wild_headline,
    )
    await _add_route_note(
        session_maker,
        origin_iso="US",
        destination_iso=dest,
        headline=specific_headline,
    )
    resp = await client.get(f"/api/route-notes?origin=US&destination={dest}")
    mine = {wild_headline, specific_headline}
    matched = [n for n in resp.json() if n["headline"] in mine]
    assert len(matched) == 2
    # Specific match comes first (rank tuple).
    assert matched[0]["origin_iso"] == "US"
    assert matched[1]["origin_iso"] == "*"


async def test_platform_notices_active_by_surface(client, session_maker):
    from app.models.notices import NoticeSurface

    key = f"footer.{uuid.uuid4().hex[:6]}"
    await _add_platform_notice(
        session_maker,
        key=key,
        target_surface=NoticeSurface.footer,
        headline="Footer platform notice",
    )
    resp = await client.get("/api/platform-notices?surface=footer")
    body = resp.json()
    row = next((n for n in body if n["key"] == key), None)
    assert row is not None
    assert row["headline"] == "Footer platform notice"


async def test_platform_notices_all_surface_matches_any_filter(client, session_maker):
    """`target_surface='all'` note must appear regardless of surface filter."""
    from app.models.notices import NoticeSurface

    key = f"all.{uuid.uuid4().hex[:6]}"
    await _add_platform_notice(
        session_maker, key=key, target_surface=NoticeSurface.all
    )
    for surface in ("footer", "trip_card", "deal_page"):
        resp = await client.get(f"/api/platform-notices?surface={surface}")
        keys = {n["key"] for n in resp.json()}
        assert key in keys, f"'all' notice not matched for surface={surface}"


async def test_endpoints_public_no_auth_required(client, session_maker):
    """Both endpoints must respond without Authorization header."""
    r1 = await client.get("/api/route-notes")
    assert r1.status_code == 200
    r2 = await client.get("/api/platform-notices")
    assert r2.status_code == 200


async def test_platform_notices_invalid_surface_rejected(client):
    """T_TEST.4 regression — invalid `surface` param must 422, not 500.

    Found by schemathesis fuzz: string 'null' was passed straight to a
    Postgres enum comparison → asyncpg InvalidTextRepresentation → 500.
    Fix: typed as NoticeSurface so FastAPI validates before DB call.
    """
    r = await client.get("/api/platform-notices?surface=not_a_valid_surface")
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────────────────────
# T_UX.2 pt.2 — superuser CRUD tests
# ─────────────────────────────────────────────────────────────


async def _register_and_promote_superuser(client, session_maker) -> dict:
    from sqlalchemy import select

    from app.models.user import User
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("adm")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "Adm"},
    )
    async with session_maker() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        u.role = "superuser"
        await db.commit()
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_create_route_note_superuser(client, session_maker):
    hdr = await _register_and_promote_superuser(client, session_maker)
    unique_headline = f"US→IR {uuid.uuid4().hex[:6]}"
    r = await client.post(
        "/api/admin/route-notes",
        headers=hdr,
        json={
            "origin_iso": "US",
            "destination_iso": "IR",
            "status": "complex",
            "severity": "warning",
            "headline": unique_headline,
            "body": "Details on sanctions.",
        },
    )
    assert r.status_code == 201, r.json()
    assert r.json()["headline"] == unique_headline
    assert r.json()["body"] == "Details on sanctions."


async def test_create_route_note_forbidden_for_non_superuser(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("usr")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "Usr"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await client.post(
        "/api/admin/route-notes",
        headers=hdr,
        json={
            "origin_iso": "US",
            "destination_iso": "IR",
            "status": "attention",
            "severity": "info",
            "headline": "x",
            "body": "y",
        },
    )
    assert r.status_code == 403


async def test_delete_route_note_removes_row(client, session_maker):
    hdr = await _register_and_promote_superuser(client, session_maker)
    note_id = await _add_route_note(
        session_maker, headline=f"del-{uuid.uuid4().hex[:6]}"
    )
    r = await client.delete(f"/api/admin/route-notes/{note_id}", headers=hdr)
    assert r.status_code == 204
    r2 = await client.get("/api/route-notes")
    assert not any(n["id"] == str(note_id) for n in r2.json())


async def test_create_platform_notice_key_conflict(client, session_maker):
    hdr = await _register_and_promote_superuser(client, session_maker)
    key = f"unique.{uuid.uuid4().hex[:6]}"
    r1 = await client.post(
        "/api/admin/platform-notices",
        headers=hdr,
        json={
            "key": key,
            "severity": "info",
            "target_surface": "footer",
            "headline": "First",
        },
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/admin/platform-notices",
        headers=hdr,
        json={
            "key": key,
            "severity": "info",
            "target_surface": "footer",
            "headline": "Dup",
        },
    )
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────
# T_UX.2 pt.4 — pin RouteNote as DealVault system-message on match
# ─────────────────────────────────────────────────────────────


async def test_match_pins_route_note_when_corridor_flagged(client, session_maker):
    """POST /deals/match on a corridor with a complex/restricted RouteNote
    must post a pinned system-message into the DealVault."""
    from sqlalchemy import select

    from app.models.deal import DealVaultMessage
    from app.models.marketplace import Trip, TripStatus
    from app.models.notices import NoticeSeverity, RouteStatus
    from app.models.user import User
    from tests.conftest import SEED_PASSWORD, unique_email

    unique_origin = f"O{uuid.uuid4().hex[:2].upper()}"
    unique_dest = f"D{uuid.uuid4().hex[:2].upper()}"
    corridor_headline = f"Flagged-{uuid.uuid4().hex[:6]}"

    await _add_route_note(
        session_maker,
        origin_iso=unique_origin,
        destination_iso=unique_dest,
        status=RouteStatus.complex,
        severity=NoticeSeverity.warning,
        headline=corridor_headline,
        body="Extra scrutiny by customs.",
    )

    carrier_email = unique_email("carrier")
    sender_email = unique_email("sender")
    await client.post(
        "/api/auth/register",
        json={
            "email": carrier_email,
            "password": SEED_PASSWORD,
            "display_name": "Carrier",
            "can_carry": True,
        },
    )
    login_c = await client.post(
        "/api/auth/login", json={"login": carrier_email, "password": SEED_PASSWORD}
    )
    carrier_hdr = {"Authorization": f"Bearer {login_c.json()['access_token']}"}

    trip_resp = await client.post(
        "/api/trips",
        headers=carrier_hdr,
        json={
            "origin": unique_origin,
            "destination": unique_dest,
            "depart_at": (datetime.now(tz=timezone.utc) + timedelta(days=2)).isoformat(),
            "arrive_at": (datetime.now(tz=timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 5,
        },
    )
    assert trip_resp.status_code == 201, trip_resp.json()
    trip_id = trip_resp.json()["id"]

    await client.post(
        "/api/auth/register",
        json={
            "email": sender_email,
            "password": SEED_PASSWORD,
            "display_name": "Sender",
        },
    )
    login_s = await client.post(
        "/api/auth/login", json={"login": sender_email, "password": SEED_PASSWORD}
    )
    sender_hdr = {"Authorization": f"Bearer {login_s.json()['access_token']}"}

    match_resp = await client.post(
        "/api/deals/match",
        headers=sender_hdr,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+79990000001",
                "origin": unique_origin,
                "destination": unique_dest,
                "category": "docs",
                "declared_value": 100,
                "currency": "USD",
                "description": "test",
            },
        },
    )
    assert match_resp.status_code == 201, match_resp.json()
    deal_id = match_resp.json()["id"]

    async with session_maker() as db:
        msgs = (
            await db.execute(
                select(DealVaultMessage)
                .where(DealVaultMessage.deal_id == uuid.UUID(deal_id))
                .where(DealVaultMessage.is_system.is_(True))
            )
        ).scalars().all()
    assert len(msgs) == 1, f"expected 1 system-message, got {len(msgs)}"
    body = msgs[0].text or ""
    assert corridor_headline in body
    assert "Extra scrutiny" in body


async def test_match_does_not_pin_when_corridor_standard(client, session_maker):
    """No system-message should be posted when the corridor has no flagged
    notes."""
    from sqlalchemy import select

    from app.models.deal import DealVaultMessage
    from tests.conftest import SEED_PASSWORD, unique_email

    origin = f"P{uuid.uuid4().hex[:2].upper()}"
    dest = f"Q{uuid.uuid4().hex[:2].upper()}"

    carrier_email = unique_email("cc")
    sender_email = unique_email("ss")
    await client.post(
        "/api/auth/register",
        json={
            "email": carrier_email,
            "password": SEED_PASSWORD,
            "display_name": "C",
            "can_carry": True,
        },
    )
    login_c = await client.post(
        "/api/auth/login", json={"login": carrier_email, "password": SEED_PASSWORD}
    )
    hdr_c = {"Authorization": f"Bearer {login_c.json()['access_token']}"}
    trip = await client.post(
        "/api/trips",
        headers=hdr_c,
        json={
            "origin": origin,
            "destination": dest,
            "depart_at": (datetime.now(tz=timezone.utc) + timedelta(days=2)).isoformat(),
            "arrive_at": (datetime.now(tz=timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 5,
        },
    )
    trip_id = trip.json()["id"]

    await client.post(
        "/api/auth/register",
        json={"email": sender_email, "password": SEED_PASSWORD, "display_name": "S"},
    )
    login_s = await client.post(
        "/api/auth/login", json={"login": sender_email, "password": SEED_PASSWORD}
    )
    hdr_s = {"Authorization": f"Bearer {login_s.json()['access_token']}"}
    match = await client.post(
        "/api/deals/match",
        headers=hdr_s,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+79990000002",
                "origin": origin,
                "destination": dest,
                "category": "docs",
                "declared_value": 10,
                "currency": "USD",
                "description": "x",
            },
        },
    )
    assert match.status_code == 201
    deal_id = match.json()["id"]

    async with session_maker() as db:
        msgs = (
            await db.execute(
                select(DealVaultMessage)
                .where(DealVaultMessage.deal_id == uuid.UUID(deal_id))
                .where(DealVaultMessage.is_system.is_(True))
            )
        ).scalars().all()
    assert msgs == []
