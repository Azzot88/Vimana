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
            headline_i18n_key=overrides.get("headline_i18n_key", "notes.us_ir.headline"),
            body_i18n_key=overrides.get("body_i18n_key", "notes.us_ir.body"),
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
            active_from=overrides.get(
                "active_from", datetime.now(tz=timezone.utc) - timedelta(hours=1)
            ),
            active_until=overrides.get("active_until"),
        )
        db.add(n)
        await db.commit()
        return n.id


async def test_route_notes_returns_active_specific_match(client, session_maker):
    await _add_route_note(
        session_maker,
        origin_iso="US",
        destination_iso="IR",
        headline_i18n_key=f"h.{uuid.uuid4().hex[:6]}",
    )
    resp = await client.get("/api/route-notes?origin=US&destination=IR")
    assert resp.status_code == 200
    body = resp.json()
    assert any(
        n["origin_iso"] == "US" and n["destination_iso"] == "IR" for n in body
    )


async def test_route_notes_wildcard_matches_any_origin(client, session_maker):
    """Note with origin='*' must match a specific origin filter."""
    from app.models.notices import RouteNote, RouteStatus

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
    unique_key = f"expired.{uuid.uuid4().hex[:6]}"
    await _add_route_note(
        session_maker,
        origin_iso="DE",
        destination_iso="CU",
        headline_i18n_key=unique_key,
        active_until=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    resp = await client.get("/api/route-notes?origin=DE&destination=CU")
    keys = {n["headline_i18n_key"] for n in resp.json()}
    assert unique_key not in keys


async def test_route_notes_ranks_specific_before_wildcards(client, session_maker):
    """Overlap: `*→IR` + `US→IR` — both returned, specific first."""
    from app.models.notices import RouteNote

    dest = f"X{uuid.uuid4().hex[:2].upper()}"
    await _add_route_note(
        session_maker,
        origin_iso="*",
        destination_iso=dest,
        headline_i18n_key=f"wild.{uuid.uuid4().hex[:6]}",
    )
    await _add_route_note(
        session_maker,
        origin_iso="US",
        destination_iso=dest,
        headline_i18n_key=f"specific.{uuid.uuid4().hex[:6]}",
    )
    resp = await client.get(f"/api/route-notes?origin=US&destination={dest}")
    matched = [n for n in resp.json() if n["destination_iso"] == dest]
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
    )
    resp = await client.get("/api/platform-notices?surface=footer")
    keys = {n["key"] for n in resp.json()}
    assert key in keys


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
