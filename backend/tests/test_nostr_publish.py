"""T3.5 — Nostr event build + toggle + endpoint."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.core.keypair import verify_event_id
from app.core.nostr_publish import (
    NOSTR_KIND_TRIP,
    build_platform_trip_event,
    is_publish_enabled,
    platform_publish_pubkey,
)
from app.core.signing import compute_event_id


async def _register_carrier(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("np-c")
    await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": SEED_PASSWORD,
            "display_name": "NPC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_publish_disabled_by_default():
    os.environ.pop("NOSTR_PUBLISH_ENABLED", None)
    assert is_publish_enabled() is False


def test_publish_enabled_when_env_set():
    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        assert is_publish_enabled() is True
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)


async def test_build_event_produces_valid_nip01_signature(client, session_maker):
    from sqlalchemy import select

    from app.models.marketplace import Trip
    from app.models.user import User

    hdr = await _register_carrier(client)
    trip = await client.post(
        "/api/trips",
        headers=hdr,
        json={
            "origin": "NEO",
            "destination": "SFO",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "capacity": 3.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201
    trip_id = trip.json()["id"]

    async with session_maker() as db:
        t = await db.get(Trip, trip_id)
        carrier = await db.get(User, t.carrier_id)
        event = build_platform_trip_event(t, carrier, "https://vimana.dealvault.club")

    assert event is not None
    assert event["kind"] == NOSTR_KIND_TRIP
    # T3.12 — authored by the platform, never by the carrier's service key.
    assert event["pubkey"] == platform_publish_pubkey()
    assert event["pubkey"] != carrier.nostr_pubkey
    # Recomputed id must match embedded id, and sig must verify against it.
    recomputed = compute_event_id(
        event["pubkey"],
        event["created_at"],
        event["kind"],
        event["tags"],
        event["content"],
    )
    assert recomputed == event["id"]
    assert verify_event_id(event["id"], event["sig"], event["pubkey"])

    # Structural: expected tags present.
    kinds = {tag[0] for tag in event["tags"]}
    assert {"d", "l", "t", "published_at", "expires_at", "capacity"} <= kinds

    # Content parses as JSON.
    parsed = json.loads(event["content"])
    assert parsed["origin"] == "NEO"
    assert parsed["destination"] == "SFO"


async def test_nostr_event_endpoint_503_when_disabled(client):
    os.environ.pop("NOSTR_PUBLISH_ENABLED", None)
    hdr = await _register_carrier(client)
    trip = await client.post(
        "/api/trips",
        headers=hdr,
        json={
            "origin": "DIS",
            "destination": "OFF",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]
    resp = await client.get(f"/api/trips/{trip_id}/nostr-event", headers=hdr)
    assert resp.status_code == 503


async def test_nostr_event_endpoint_returns_event_when_enabled(client):
    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        hdr = await _register_carrier(client)
        trip = await client.post(
            "/api/trips",
            headers=hdr,
            json={
                "origin": "ONO",
                "destination": "STR",
                "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "capacity": 2.0,
                "allowed_categories": ["document"],
            },
        )
        trip_id = trip.json()["id"]
        resp = await client.get(f"/api/trips/{trip_id}/nostr-event", headers=hdr)
        assert resp.status_code == 200
        event = resp.json()
        assert event["kind"] == NOSTR_KIND_TRIP
        assert verify_event_id(event["id"], event["sig"], event["pubkey"])
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)


async def test_publish_task_skips_a_carrier_who_owns_their_key(
    client, session_maker, sync_sessions, monkeypatch
):
    """T3.12 — the platform publishes *for* keyless carriers only. Once a
    carrier holds their own key they publish themselves over NIP-07, and the
    server has nothing it could sign with on their behalf."""
    import os

    from app.models.marketplace import Trip
    from app.tasks.nostr_publish import publish_trip_to_nostr

    hdr = await _register_carrier(client)
    claim = await client.post("/api/me/keypair/claim", headers=hdr)
    assert claim.status_code == 200

    trip = await client.post(
        "/api/trips",
        headers=hdr,
        json={
            "origin": "SLF",
            "destination": "CST",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        result = publish_trip_to_nostr(trip_id)
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)

    assert "skipped" in result
    assert "own" in result["skipped"]

    async with session_maker() as db:
        t = await db.get(Trip, trip_id)
        assert t.nostr_event_id is None


async def test_trip_out_exposes_nostr_fields(client):
    hdr = await _register_carrier(client)
    trip = await client.post(
        "/api/trips",
        headers=hdr,
        json={
            "origin": "OUT",
            "destination": "SCH",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201
    body = trip.json()
    # Fields exist (may be None until publish task runs).
    assert "nostr_event_id" in body
    assert "nostr_published_at" in body
