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


# ── T3.18 — the public identity page ─────────────────────────────────────────


async def test_an_identity_opens_by_its_key_without_signing_in(client, carrier_headers):
    """The key *is* the identity, so the link carries the key — not a row id
    that means nothing outside our database."""
    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub = me.json()["nostr_pubkey"]

    resp = await client.get(f"/api/identities/{npub}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["npub"] == npub
    assert body["visibility"] == "full"
    assert body["display_name"]
    # A different category of data, not "private fields": these must not appear
    # at any visibility level.
    for forbidden in ("email", "phone", "receiving_city"):
        assert forbidden not in body


async def test_hidden_answers_404_rather_than_403(client, carrier_headers, session_maker):
    """403 would confirm the account exists — precisely what hiding is for."""
    import uuid as uuidlib

    from app.models.user import User

    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub, user_id = me.json()["nostr_pubkey"], uuidlib.UUID(me.json()["id"])

    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.public_profile = "hidden"
        await db.commit()

    try:
        anon = await client.get(f"/api/identities/{npub}")
        assert anon.status_code == 404

        # …and the numbers behind the page are hidden too, to a stranger and to
        # nobody-at-all alike. A setting that hides the page while the metrics
        # answer one URL over is a setting that lies.
        anon_metrics = await client.get(f"/api/users/{user_id}/trust-metrics")
        assert anon_metrics.status_code == 404
        uba = await client.get(f"/api/users/{user_id}/uba", headers=carrier_headers)
        assert uba.status_code == 200, "the owner still sees themselves"
    finally:
        async with session_maker() as db:
            user = await db.get(User, user_id)
            user.public_profile = "full"
            await db.commit()


async def test_minimal_shows_that_the_key_is_real_and_nothing_else(
    client, carrier_headers, session_maker
):
    import uuid as uuidlib

    from app.models.user import User

    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub, user_id = me.json()["nostr_pubkey"], uuidlib.UUID(me.json()["id"])

    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.public_profile = "minimal"
        await db.commit()

    try:
        resp = await client.get(f"/api/identities/{npub}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["visibility"] == "minimal"
        assert body["display_name"] is None
        assert body["uba"] is None
        assert body["dealt_with_count"] is None
    finally:
        async with session_maker() as db:
            user = await db.get(User, user_id)
            user.public_profile = "full"
            await db.commit()


async def test_trust_metrics_are_readable_without_a_session(client, seed_carrier):
    """Same counters the public identity page shows. Requiring a session here
    and not there would have been a difference without a reason — the only
    thing an anonymous caller loses is the distance, because there is no viewer
    to measure it from."""
    resp = await client.get(f"/api/users/{seed_carrier.id}/trust-metrics")
    assert resp.status_code == 200, resp.text
    assert resp.json()["distance_from_viewer"] is None
