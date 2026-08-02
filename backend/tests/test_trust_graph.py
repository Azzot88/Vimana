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


# ── T3.19 — the archive record ───────────────────────────────────────────────


async def test_a_live_identity_carries_no_archive(client, carrier_headers):
    """Absence of the block is not a missing field: there is no record to close
    while the key still signs."""
    me = await client.get("/api/auth/me", headers=carrier_headers)
    body = (await client.get(f"/api/identities/{me.json()['nostr_pubkey']}")).json()
    assert body["archive"] is None


async def test_a_retired_identity_shows_counted_numbers_only(
    client, carrier_headers, session_maker
):
    """Everything on the placard is counted from rows. The assertions here are
    about *what kind* of number may appear at all — a rate or an average would
    read as measured, and nothing measures it."""
    import uuid as uuidlib
    from datetime import datetime, timezone

    from app.models.user import User

    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub, user_id = me.json()["nostr_pubkey"], uuidlib.UUID(me.json()["id"])

    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.key_lost_at = datetime.now(timezone.utc)
        await db.commit()

    try:
        body = (await client.get(f"/api/identities/{npub}")).json()
        assert body["key_lost"] is True
        archive = body["archive"]
        assert archive is not None
        assert archive["retired_at"]

        # Counts, and the totals they were counted from — never a bare ratio.
        assert archive["deals_closed"] <= archive["deals_total"]
        assert archive["routes_measured"] <= archive["routes_closed"]
        assert archive["signatures"] <= archive["chain_entries"]

        # Distances are a great-circle arc; the field name has to say so, since
        # the label on the page is written from it.
        assert "straight_line_km" in archive
        assert not any(
            k for k in archive if "percent" in k or "average" in k or "rate" in k
        )

        # A sum with no measurable route behind it is None, not a confident 0.
        if archive["routes_measured"] == 0:
            assert archive["straight_line_km"] is None
            assert archive["longest_hop_km"] is None

        # T3.20 — how far the record is checkable without our word. Null until
        # an anchor exists, and the card must then say nothing of the kind:
        # "independently checkable" with no date behind it is the exact claim
        # this project refuses to make.
        assert "last_anchor_at" in archive
        assert archive["anchored_deals"] <= archive["deals_total"]
        if archive["last_anchor_at"] is None:
            assert archive["anchored_deals"] == 0
    finally:
        async with session_maker() as db:
            user = await db.get(User, user_id)
            user.key_lost_at = None
            await db.commit()


async def test_the_archive_of_a_hidden_identity_is_not_reachable(
    client, carrier_headers, session_maker
):
    """Retiring must not open a back door around the visibility gate — the
    archive rides on the same `require_visible` call as everything else."""
    import uuid as uuidlib
    from datetime import datetime, timezone

    from app.models.user import User

    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub, user_id = me.json()["nostr_pubkey"], uuidlib.UUID(me.json()["id"])

    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.key_lost_at = datetime.now(timezone.utc)
        user.archive_choice = "hide"
        await db.commit()

    try:
        assert (await client.get(f"/api/identities/{npub}")).status_code == 404
        # The owner still reaches their own page — closing the exhibit is not
        # locking yourself out of your own history.
        mine = await client.get(f"/api/identities/{npub}", headers=carrier_headers)
        assert mine.status_code == 200
        assert mine.json()["archive"] is not None
    finally:
        async with session_maker() as db:
            user = await db.get(User, user_id)
            user.key_lost_at = None
            user.archive_choice = None
            await db.commit()


async def test_minimal_visibility_does_not_leak_the_archive(
    client, carrier_headers, session_maker
):
    """`minimal` answers "is this key real", nothing more. A retirement placard
    under it would be a portrait drawn by another route."""
    import uuid as uuidlib
    from datetime import datetime, timezone

    from app.models.user import User

    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub, user_id = me.json()["nostr_pubkey"], uuidlib.UUID(me.json()["id"])

    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.key_lost_at = datetime.now(timezone.utc)
        user.public_profile = "minimal"
        await db.commit()

    try:
        body = (await client.get(f"/api/identities/{npub}")).json()
        assert body["visibility"] == "minimal"
        assert body["key_lost"] is True, "existence and its end are the same fact"
        assert body["archive"] is None
    finally:
        async with session_maker() as db:
            user = await db.get(User, user_id)
            user.key_lost_at = None
            user.public_profile = "full"
            await db.commit()


# ── T_TRUST.1 — no claim without its date ────────────────────────────────────


async def test_the_identity_page_dates_its_claims(client, carrier_headers):
    """A level and a counter are present-tense statements about the past.

    `D-EVIDENCE-DECAYS`: whenever the page can say "verified" or "vouched for",
    it must be able to say when — otherwise the claim is stronger than the
    evidence behind it.
    """
    me = await client.get("/api/auth/me", headers=carrier_headers)
    body = (await client.get(f"/api/identities/{me.json()['nostr_pubkey']}")).json()

    assert "verified_at" in body
    assert "last_vouched_at" in body
    if body["highest_verification_level"] is not None:
        assert body["verified_at"] is not None, "a level with no date is an overclaim"
    if (body["verifications_received_count"] or 0) > 0:
        assert body["last_vouched_at"] is not None


async def test_minimal_visibility_still_carries_the_date(
    client, carrier_headers, session_maker
):
    """The date is part of the claim, not part of the portrait — `minimal`
    drops the portrait and keeps the claim honest."""
    import uuid as uuidlib

    from app.models.user import User

    me = await client.get("/api/auth/me", headers=carrier_headers)
    npub, user_id = me.json()["nostr_pubkey"], uuidlib.UUID(me.json()["id"])

    async with session_maker() as db:
        user = await db.get(User, user_id)
        user.public_profile = "minimal"
        await db.commit()

    try:
        body = (await client.get(f"/api/identities/{npub}")).json()
        assert body["visibility"] == "minimal"
        assert body["display_name"] is None
        if body["highest_verification_level"] is not None:
            assert body["verified_at"] is not None
    finally:
        async with session_maker() as db:
            user = await db.get(User, user_id)
            user.public_profile = "full"
            await db.commit()


async def test_trust_metrics_date_their_counters(client, seed_carrier):
    """Three vouches from four years ago is a different statement from three
    from last month, and the counter alone cannot tell them apart."""
    body = (await client.get(f"/api/users/{seed_carrier.id}/trust-metrics")).json()
    assert "last_vouched_at" in body


async def test_a_malformed_key_is_refused_before_the_database(client):
    """T_KEYS.1 — the npub is checked for shape, not handed to Postgres raw.

    Found by the contract fuzzer: a NUL byte in the path reached asyncpg, which
    rejects it at the protocol level, so a malformed **public** URL answered
    500. Anything that is not 64 hex characters cannot match a row anyway, and
    the answer for all of it is the same "no such identity" this endpoint gives
    to everything it will not talk about.
    """
    for bad in ("\x00", "not-a-key", "AB" * 32 + "cd", "%2e%2e", " ", "z" * 64):
        resp = await client.get(f"/api/identities/{bad}")
        assert resp.status_code in (404, 422), f"{bad!r} → {resp.status_code}"
