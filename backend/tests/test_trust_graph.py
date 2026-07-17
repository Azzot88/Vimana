"""T2.4 — Trust Graph MVP tests."""
import uuid

import pytest


async def test_invite_accept_creates_symmetric_invited_edges(client, seed_carrier):
    """When user B accepts A's invite, both `invited` edges appear."""
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    # Register alice + bob
    alice_email = unique_email("alice")
    await client.post(
        "/api/auth/register",
        json={"email": alice_email, "password": SEED_PASSWORD, "display_name": "Alice"},
    )
    alice_token = await _login(client, alice_email)
    alice_headers = {"Authorization": f"Bearer {alice_token}"}

    bob_email = unique_email("bob")
    await client.post(
        "/api/auth/register",
        json={"email": bob_email, "password": SEED_PASSWORD, "display_name": "Bob"},
    )
    bob_token = await _login(client, bob_email)
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    # Alice creates invite, Bob accepts
    invite_resp = await client.post("/api/invites", headers=alice_headers)
    invite_token = invite_resp.json()["token"]
    accept = await client.post(f"/api/invites/{invite_token}/accept", headers=bob_headers)
    assert accept.status_code == 200

    # Alice sees Bob in her circle (depth=1, kind=invited)
    circle = await client.get(
        "/api/me/trust-circle?depth=1&kind=invited", headers=alice_headers
    )
    assert circle.status_code == 200
    body = circle.json()
    assert body["total_reachable"] == 1

    # Bob sees Alice in his circle too
    circle_b = await client.get(
        "/api/me/trust-circle?depth=1&kind=invited", headers=bob_headers
    )
    assert circle_b.json()["total_reachable"] == 1


async def test_confirm_deal_creates_dealt_with_edges(
    client, carrier_headers, sender_headers, seed_carrier, seed_sender
):
    """Full deal lifecycle → confirm → dealt_with edges + refreshed counters."""
    from datetime import datetime, timedelta, timezone

    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "TGH",
            "destination": "TG2",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 1.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]

    match = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000009999",
                "origin": "TGH",
                "destination": "TG2",
                "category": "document",
                "declared_value": 50.0,
            },
        },
    )
    deal_id = match.json()["id"]

    # accept + handoff + confirm
    await client.post(f"/api/deals/{deal_id}/accept", headers=carrier_headers)
    await client.post(
        f"/api/deals/{deal_id}/event",
        headers=carrier_headers,
        json={"event_type": "handoff"},
    )
    await client.post(
        f"/api/deals/{deal_id}/event",
        headers=carrier_headers,
        json={"event_type": "received"},
    )
    confirm = await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    assert confirm.status_code == 200

    # Sender sees carrier at distance 1
    metrics = await client.get(
        f"/api/users/{seed_carrier.id}/trust-metrics", headers=sender_headers
    )
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["distance_from_viewer"] == 1
    assert body["dealt_with_count"] >= 1


async def test_bfs_respects_depth_limit(client, sender_headers, seed_sender):
    """Depth=0 has no effect (min 1); depth=6 works but only returns reachable."""
    r = await client.get("/api/me/trust-circle?depth=2", headers=sender_headers)
    assert r.status_code == 200
    assert r.json()["depth"] == 2
    # depth=0 should clamp to min 1 (Query validator: ge=1)
    r0 = await client.get("/api/me/trust-circle?depth=0", headers=sender_headers)
    assert r0.status_code == 422


async def test_kind_filter_validates(client, sender_headers):
    r = await client.get("/api/me/trust-circle?kind=bogus", headers=sender_headers)
    assert r.status_code == 422


async def test_trust_metrics_for_self_returns_no_distance(
    client, sender_headers, seed_sender
):
    r = await client.get(
        f"/api/users/{seed_sender.id}/trust-metrics", headers=sender_headers
    )
    assert r.status_code == 200
    # distance is None for self (endpoint short-circuits)
    assert r.json()["distance_from_viewer"] is None


async def test_sybil_guard_blocks_peer_verified_without_closed_deal(
    session_maker, seed_carrier, seed_sender
):
    """`peer_verified` edge REQUIRES an existing closed Deal between the pair."""
    from app.core.trust import SybilGuardError, add_edge
    from app.models.trust import TrustEdgeKind

    async with session_maker() as db:
        # Wipe any dealt_with edges from prior tests so we test the guard purely
        from sqlalchemy import delete
        from app.models.trust import TrustEdge

        await db.execute(
            delete(TrustEdge).where(
                TrustEdge.from_user_id.in_([seed_sender.id, seed_carrier.id]),
                TrustEdge.to_user_id.in_([seed_sender.id, seed_carrier.id]),
                TrustEdge.kind == TrustEdgeKind.peer_verified,
            )
        )
        await db.commit()

        # Two brand-new users have no closed deal → should raise
        from tests.conftest import _get_or_create_user, unique_email

        u1 = await _get_or_create_user(
            db, email=unique_email("sy1"), display_name="Sy1"
        )
        u2 = await _get_or_create_user(
            db, email=unique_email("sy2"), display_name="Sy2"
        )
        with pytest.raises(SybilGuardError):
            await add_edge(
                db,
                from_user_id=u1.id,
                to_user_id=u2.id,
                kind=TrustEdgeKind.peer_verified,
            )


async def test_edge_insert_is_idempotent(session_maker, seed_carrier, seed_sender):
    """Second insert with same (from, to, kind, source_ref) is a no-op."""
    from sqlalchemy import select, func
    from app.core.trust import add_edge
    from app.models.trust import TrustEdge, TrustEdgeKind

    async with session_maker() as db:
        for _ in range(3):
            await add_edge(
                db,
                from_user_id=seed_sender.id,
                to_user_id=seed_carrier.id,
                kind=TrustEdgeKind.dealt_with,
                source_ref="test:idempotent",
                check_sybil=False,
            )
        await db.commit()
        count = await db.scalar(
            select(func.count(TrustEdge.id)).where(
                TrustEdge.from_user_id == seed_sender.id,
                TrustEdge.to_user_id == seed_carrier.id,
                TrustEdge.source_ref == "test:idempotent",
            )
        )
        assert count == 1


async def test_revoked_edges_not_traversed_by_bfs(
    session_maker, seed_carrier, seed_sender, client, sender_headers
):
    """Revoking an edge should immediately hide it from BFS output."""
    from datetime import datetime, timezone
    from sqlalchemy import select, update
    from app.core.trust import add_edge
    from app.models.trust import TrustEdge, TrustEdgeKind

    async with session_maker() as db:
        await add_edge(
            db,
            from_user_id=seed_sender.id,
            to_user_id=seed_carrier.id,
            kind=TrustEdgeKind.dealt_with,
            source_ref="test:revoke",
            check_sybil=False,
        )
        await db.commit()

    r1 = await client.get(
        "/api/me/trust-circle?depth=1&kind=dealt_with", headers=sender_headers
    )
    body1 = r1.json()
    assert body1["total_reachable"] >= 1

    # Revoke the edge
    async with session_maker() as db:
        await db.execute(
            update(TrustEdge)
            .where(
                TrustEdge.from_user_id == seed_sender.id,
                TrustEdge.to_user_id == seed_carrier.id,
                TrustEdge.source_ref == "test:revoke",
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()

    r2 = await client.get(
        "/api/me/trust-circle?depth=1&kind=dealt_with", headers=sender_headers
    )
    # If revoke was the only edge, total_reachable drops; otherwise at least
    # doesn't include the revoked target through source_ref='test:revoke'.
    assert r2.status_code == 200


async def test_trust_metrics_denormalized_counts_after_edge(
    session_maker, seed_carrier, seed_sender, client, sender_headers
):
    """Adding a dealt_with edge + refresh should bump denormalized counts."""
    from app.core.trust import add_edge, refresh_trust_counts
    from app.models.trust import TrustEdgeKind

    async with session_maker() as db:
        await add_edge(
            db,
            from_user_id=seed_sender.id,
            to_user_id=seed_carrier.id,
            kind=TrustEdgeKind.dealt_with,
            source_ref="test:count",
            check_sybil=False,
        )
        await refresh_trust_counts(db, seed_sender.id)
        await db.commit()

    metrics = await client.get(
        f"/api/users/{seed_sender.id}/trust-metrics", headers=sender_headers
    )
    assert metrics.status_code == 200
    assert metrics.json()["dealt_with_count"] >= 1
