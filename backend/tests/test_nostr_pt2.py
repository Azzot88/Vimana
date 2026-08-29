"""T3.5 pt.2 — NIP-07 publish + metrics + republish + WoT whitelist."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from tests.conftest import make_account


async def _register(client, prefix: str, *, carrier: bool = False) -> tuple[dict, str]:
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email(prefix)
    payload = {
        "email": email,
        "password": SEED_PASSWORD,
        "display_name": prefix.upper(),
    }
    if carrier:
        payload.update({"can_carry": True, "active_mode": "carrier"})
    await make_account(payload)
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, email


async def _make_trip(client, hdr) -> str:
    resp = await client.post(
        "/api/trips",
        headers=hdr,
        json={
            "origin": "P2X",
            "destination": "P2Y",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    return resp.json()["id"]


async def test_publish_signed_flow_end_to_end(client, session_maker):
    """Custodial carrier — we sign locally using the exposed nsec — this is the
    same shape the frontend NIP-07 extension will produce."""
    from app.core.keypair import sign_event_id
    from app.core.nostr_publish import NOSTR_KIND_TRIP
    from app.core.signing import compute_event_id
    from app.models.marketplace import Trip
    from app.models.user import User
    from tests.conftest import SEED_PASSWORD

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    os.environ["NOSTR_FRIENDLY_RELAYS"] = ""  # no outbound calls in tests
    try:
        from tests.conftest import establish_identity

        hdr, email = await _register(client, "sp-c", carrier=True)
        # T3.12 — the test generates the key and proves possession, exactly as a
        # browser would. The server discloses nothing.
        keys = await establish_identity(client, hdr)

        trip_id = await _make_trip(client, hdr)
        async with session_maker() as db:
            trip = await db.get(Trip, trip_id)
            depart_ts = int(trip.depart_at.timestamp())

        created_at = int(datetime.now(tz=timezone.utc).timestamp())
        tags = [
            ["d", trip_id],
            ["l", "P2X"],
            ["l", "P2Y"],
            ["t", "vimana"],
            ["t", "trip"],
            ["published_at", str(created_at)],
            ["expires_at", str(depart_ts)],
            ["capacity", "2.0kg"],
            ["t", "document"],
        ]
        content = json.dumps(
            {
                "origin": "P2X",
                "destination": "P2Y",
                "depart_at": trip.depart_at.isoformat(),
                "capacity": 2.0,
                "allowed_categories": ["document"],
                "carrier_pubkey": None,
                "platform_url": "https://vimana.dealvault.club",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        # Match exactly what backend build_event uses (see core.nostr_publish).
        event_id = compute_event_id(
            keys["npub_hex"], created_at, NOSTR_KIND_TRIP, tags, content
        )
        sig = sign_event_id(event_id, keys["nsec_hex"])

        resp = await client.post(
            "/api/nostr/publish-signed",
            headers=hdr,
            json={
                "trip_id": trip_id,
                "id": event_id,
                "pubkey": keys["npub_hex"],
                "created_at": created_at,
                "kind": NOSTR_KIND_TRIP,
                "tags": tags,
                "content": content,
                "sig": sig,
            },
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["event_id"] == event_id

        # DB got the id stamped.
        async with session_maker() as db:
            trip = await db.get(Trip, trip_id)
            assert trip.nostr_event_id == event_id
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)
        os.environ.pop("NOSTR_FRIENDLY_RELAYS", None)


async def test_publish_signed_rejects_bad_sig(client, session_maker):
    from app.core.nostr_publish import NOSTR_KIND_TRIP
    from app.core.signing import compute_event_id
    from tests.conftest import SEED_PASSWORD

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        from tests.conftest import establish_identity

        hdr, _ = await _register(client, "bad-c", carrier=True)
        keys = await establish_identity(client, hdr)
        trip_id = await _make_trip(client, hdr)
        created_at = int(datetime.now(tz=timezone.utc).timestamp())
        tags = [["d", trip_id]]
        content = "x"
        event_id = compute_event_id(
            keys["npub_hex"], created_at, NOSTR_KIND_TRIP, tags, content
        )
        resp = await client.post(
            "/api/nostr/publish-signed",
            headers=hdr,
            json={
                "trip_id": trip_id,
                "id": event_id,
                "pubkey": keys["npub_hex"],
                "created_at": created_at,
                "kind": NOSTR_KIND_TRIP,
                "tags": tags,
                "content": content,
                "sig": "00" * 64,  # invalid
            },
        )
        assert resp.status_code == 422
        assert "signature" in resp.json()["detail"].lower()
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)


async def test_publish_signed_rejects_wrong_pubkey(client):
    from app.core.nostr_publish import NOSTR_KIND_TRIP
    from tests.conftest import SEED_PASSWORD

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        hdr, _ = await _register(client, "wp-c", carrier=True)
        trip_id = await _make_trip(client, hdr)
        resp = await client.post(
            "/api/nostr/publish-signed",
            headers=hdr,
            json={
                "trip_id": trip_id,
                "id": "0" * 64,
                "pubkey": "1" * 64,  # not caller's npub
                "created_at": 0,
                "kind": NOSTR_KIND_TRIP,
                "tags": [],
                "content": "",
                "sig": "0" * 128,
            },
        )
        assert resp.status_code == 422
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)


async def test_publish_signed_forbids_third_party(client):
    """Only the trip's carrier can publish its event."""
    from app.core.nostr_publish import NOSTR_KIND_TRIP

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        c_hdr, _ = await _register(client, "own-c", carrier=True)
        trip_id = await _make_trip(client, c_hdr)
        other_hdr, _ = await _register(client, "other")
        resp = await client.post(
            "/api/nostr/publish-signed",
            headers=other_hdr,
            json={
                "trip_id": trip_id,
                "id": "0" * 64,
                "pubkey": "1" * 64,
                "created_at": 0,
                "kind": NOSTR_KIND_TRIP,
                "tags": [],
                "content": "",
                "sig": "0" * 128,
            },
        )
        assert resp.status_code == 403
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)


async def test_metrics_endpoint_returns_expected_shape(client):
    """`publish_metrics` is a single row shared across the whole test session,
    so we can't assert zero — earlier publish tests may have bumped counters.
    Structural check + non-negative invariant is what actually matters."""
    hdr, _ = await _register(client, "met")
    resp = await client.get("/api/nostr/metrics", headers=hdr)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"success_count", "error_count", "last_attempt_at"}
    assert isinstance(body["success_count"], int) and body["success_count"] >= 0
    assert isinstance(body["error_count"], int) and body["error_count"] >= 0
    # last_attempt_at is either None (никогда не публиковали) или ISO string.
    assert body["last_attempt_at"] is None or isinstance(body["last_attempt_at"], str)


async def test_counter_increments_are_not_lost_and_are_read_back(session_maker):
    """T_PERF.1 — the addition happens in the database, and the reader sees it.

    Two things used to be wrong here at once. The bump was a read-modify-write
    through the ORM, so simultaneous publishes overwrote each other's `n + 1`.
    And the read went through `select(PublishMetric)`, which with
    `expire_on_commit=False` can be answered from the identity map — the very
    map that never saw the new value, because the database computed it.
    """
    from app.core.metrics import bump_publish_metric, get_publish_metrics

    async with session_maker() as db:
        before = await get_publish_metrics(db)
        await bump_publish_metric(db, success=True)
        await bump_publish_metric(db, success=True)
        await bump_publish_metric(db, success=False)
        await db.commit()
        after = await get_publish_metrics(db)

    assert after["success_count"] == before["success_count"] + 2
    assert after["error_count"] == before["error_count"] + 1
    assert after["last_attempt_at"] is not None


async def test_metrics_bump_after_publish(client, session_maker):
    """Publish (even with no relays configured → all failures) still bumps the
    error counter — that's the observability we want."""
    from app.core.keypair import sign_event_id
    from app.core.nostr_publish import NOSTR_KIND_TRIP
    from app.core.signing import compute_event_id
    from app.models.marketplace import Trip
    from tests.conftest import SEED_PASSWORD

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    os.environ["NOSTR_FRIENDLY_RELAYS"] = ""  # empty → no publish → success is vacuously false
    try:
        from tests.conftest import establish_identity

        hdr, _ = await _register(client, "mb-c", carrier=True)
        keys = await establish_identity(client, hdr)
        trip_id = await _make_trip(client, hdr)
        async with session_maker() as db:
            trip = await db.get(Trip, trip_id)
            depart_ts = int(trip.depart_at.timestamp())

        created_at = int(datetime.now(tz=timezone.utc).timestamp())
        tags = [
            ["d", trip_id], ["l", "P2X"], ["l", "P2Y"], ["t", "vimana"], ["t", "trip"],
            ["published_at", str(created_at)], ["expires_at", str(depart_ts)],
            ["capacity", "2.0kg"], ["t", "document"],
        ]
        content = json.dumps(
            {"origin": "P2X", "destination": "P2Y",
             "depart_at": trip.depart_at.isoformat(), "capacity": 2.0,
             "allowed_categories": ["document"], "carrier_pubkey": None,
             "platform_url": "https://vimana.dealvault.club"},
            separators=(",", ":"), ensure_ascii=False,
        )
        event_id = compute_event_id(keys["npub_hex"], created_at, NOSTR_KIND_TRIP, tags, content)
        sig = sign_event_id(event_id, keys["nsec_hex"])
        await client.post(
            "/api/nostr/publish-signed",
            headers=hdr,
            json={"trip_id": trip_id, "id": event_id, "pubkey": keys["npub_hex"],
                  "created_at": created_at, "kind": NOSTR_KIND_TRIP,
                  "tags": tags, "content": content, "sig": sig},
        )

        metrics = await client.get("/api/nostr/metrics", headers=hdr)
        assert metrics.status_code == 200
        body = metrics.json()
        # With no relays, publish returns empty dict — treated as "no success" → error bump.
        assert body["error_count"] >= 1
        assert body["last_attempt_at"] is not None
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)
        os.environ.pop("NOSTR_FRIENDLY_RELAYS", None)


async def test_republish_requires_superuser(client, session_maker):
    from app.models.user import User

    os.environ["NOSTR_PUBLISH_ENABLED"] = "true"
    try:
        hdr, _ = await _register(client, "rp-c", carrier=True)
        trip_id = await _make_trip(client, hdr)

        # Regular user → 403.
        resp = await client.post(
            f"/api/nostr/republish/{trip_id}", headers=hdr
        )
        assert resp.status_code == 403

        # Promote self via DB to superuser and retry.
        async with session_maker() as db:
            me = (await db.execute(
                __import__("sqlalchemy").select(User).where(
                    User.nostr_pubkey.isnot(None)
                ).order_by(User.created_at.desc()).limit(1)
            )).scalar_one()
            me.roles = ["superuser"]
            await db.commit()

        resp2 = await client.post(
            f"/api/nostr/republish/{trip_id}", headers=hdr
        )
        # 200 (relays empty → error metric bumps, but call succeeds structurally).
        assert resp2.status_code == 200
        assert resp2.json()["forced"] is True
    finally:
        os.environ.pop("NOSTR_PUBLISH_ENABLED", None)


def test_whitelist_task_writes_file(session_maker, tmp_path):
    """The Celery task itself is sync; call the function directly.
    Verifies allowed_pubkeys.txt is populated with carrier npubs that have
    at least one active trust edge."""
    from app.tasks.nostr_whitelist import refresh_allowed_pubkeys

    file_path = tmp_path / "allowed.txt"
    os.environ["NOSTR_ALLOWED_PUBKEYS_FILE"] = str(file_path)
    try:
        result = refresh_allowed_pubkeys()
        # File is written (may be empty if no eligible users in test DB).
        assert file_path.exists()
        assert "count" in result
    finally:
        os.environ.pop("NOSTR_ALLOWED_PUBKEYS_FILE", None)


def test_whitelist_includes_the_chain_anchor_key(session_maker, tmp_path, monkeypatch):
    """T3.20 — our own relay refuses anything not on this list.

    The publishing key was added in T3.5 pt.2; the anchor key is deliberately a
    different key (T3.6), so adding one did not cover the other — and every
    anchor was rejected by our own strfry before third parties even entered the
    picture. Found on the first live tick, 2026-08-01.
    """
    from app.core.keypair import generate_keypair
    from app.tasks.nostr_whitelist import refresh_allowed_pubkeys

    anchor_nsec, anchor_npub = generate_keypair()
    monkeypatch.setenv("CHAIN_ANCHOR_NSEC", anchor_nsec)
    file_path = tmp_path / "allowed.txt"
    monkeypatch.setenv("NOSTR_ALLOWED_PUBKEYS_FILE", str(file_path))

    refresh_allowed_pubkeys()
    assert anchor_npub in file_path.read_text().split()


def test_whitelist_survives_an_unconfigured_anchor(session_maker, tmp_path, monkeypatch):
    """No anchor key configured is a normal state, not an error: anchoring is
    off until someone turns it on, and the whitelist must still be written."""
    from app.tasks.nostr_whitelist import refresh_allowed_pubkeys

    monkeypatch.delenv("CHAIN_ANCHOR_NSEC", raising=False)
    file_path = tmp_path / "allowed.txt"
    monkeypatch.setenv("NOSTR_ALLOWED_PUBKEYS_FILE", str(file_path))

    result = refresh_allowed_pubkeys()
    assert file_path.exists()
    assert "count" in result
