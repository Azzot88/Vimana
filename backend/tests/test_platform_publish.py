"""T3.12 pt.3 — trips go out under the platform key, and not all of them.

Two properties are pinned here:

1. A carrier's *service* key never signs anything that leaves the platform. It
   is destroyed the moment they take their own identity, and an event signed by
   it would outlive it on relays we do not control, attributed to a pubkey that
   belongs to nobody.
2. Publication is selective. One key carrying every listing is exactly the
   shape relays throttle, so the filter is what makes the platform-key approach
   viable at all.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.keypair import generate_keypair, npub_from_nsec, verify_event_id
from app.core.nostr_publish import (
    NOSTR_KIND_TRIP,
    build_platform_deletion_event,
    build_platform_trip_event,
    platform_publish_pubkey,
)
from app.core.publish_filter import should_publish
from app.core.signing import compute_event_id
from app.models.marketplace import Trip, TripStatus
from app.models.user import User

PLATFORM_NSEC, PLATFORM_NPUB = generate_keypair()


@pytest.fixture
def platform_key(monkeypatch):
    monkeypatch.setenv("PLATFORM_PUBLISH_NSEC", PLATFORM_NSEC)
    return PLATFORM_NPUB


def _trip(carrier_id, origin="Tbilisi", destination="Ulaanbaatar") -> Trip:
    return Trip(
        id=uuid.uuid4(),
        carrier_id=carrier_id,
        origin=origin,
        destination=destination,
        depart_at=datetime.now(timezone.utc) + timedelta(days=5),
        capacity=4.0,
        allowed_categories=["documents"],
        status=TripStatus.open,
    )


def _carrier() -> User:
    nsec, npub = generate_keypair()
    return User(
        id=uuid.uuid4(),
        email="pub@vimana.test",
        display_name="Nino",
        nostr_pubkey=npub,
        key_self_custody=False,
    )


# ── platform-signed events ───────────────────────────────────────────────────


def test_event_is_authored_by_the_platform(platform_key):
    carrier = _carrier()
    event = build_platform_trip_event(_trip(carrier.id), carrier, "https://x.test")

    assert event is not None
    assert event["pubkey"] == platform_key
    assert event["pubkey"] != carrier.nostr_pubkey


def test_signature_verifies_against_the_platform_key(platform_key):
    carrier = _carrier()
    event = build_platform_trip_event(_trip(carrier.id), carrier, "https://x.test")

    recomputed = compute_event_id(
        event["pubkey"],
        event["created_at"],
        event["kind"],
        event["tags"],
        event["content"],
    )
    assert recomputed == event["id"]
    assert verify_event_id(event["id"], event["sig"], platform_key)


def test_carrier_is_named_not_impersonated(platform_key):
    """The listing says whose trip it is without claiming they signed it."""
    import json

    carrier = _carrier()
    event = build_platform_trip_event(_trip(carrier.id), carrier, "https://x.test")
    content = json.loads(event["content"])

    assert content["carrier_name"] == carrier.display_name
    assert content["carrier_pubkey"] is None, "a service key must never be published"
    assert content["published_by"] == "platform"
    assert ["published_by", "platform"] in event["tags"]
    # The carrier's own key appears nowhere in the event.
    assert carrier.nostr_pubkey not in json.dumps(event)


def test_no_platform_key_means_no_event(monkeypatch):
    monkeypatch.setenv("PLATFORM_PUBLISH_NSEC", "")
    carrier = _carrier()
    assert build_platform_trip_event(_trip(carrier.id), carrier, "https://x.test") is None
    assert platform_publish_pubkey() is None


def test_malformed_platform_key_is_ignored(monkeypatch):
    monkeypatch.setenv("PLATFORM_PUBLISH_NSEC", "not-a-key")
    assert platform_publish_pubkey() is None


def test_deletion_is_signed_by_the_same_key(platform_key):
    """NIP-09: relays honour a retraction only from the publishing key."""
    event = build_platform_deletion_event("f" * 64)

    assert event is not None
    assert event["kind"] == 5
    assert event["pubkey"] == platform_key
    assert ["e", "f" * 64] in event["tags"]
    assert ["k", str(NOSTR_KIND_TRIP)] in event["tags"]
    assert verify_event_id(event["id"], event["sig"], platform_key)


def test_platform_key_is_not_the_anchor_key(platform_key, monkeypatch):
    """T3.6 keeps the anchor key separate from user keys for the same reason:
    one signer making two different claims blurs who attests to what."""
    anchor_nsec, anchor_npub = generate_keypair()
    monkeypatch.setenv("CHAIN_ANCHOR_NSEC", anchor_nsec)
    assert platform_publish_pubkey() != anchor_npub
    assert npub_from_nsec(PLATFORM_NSEC) == platform_key


# ── the filter ───────────────────────────────────────────────────────────────


def test_filter_mode_none_blocks_everything(sync_sessions, monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_FILTER", "none")
    with sync_sessions() as db:
        ok, reason = should_publish(db, _trip(uuid.uuid4()))
    assert ok is False
    assert "none" in reason


def test_filter_mode_all_passes_everything(sync_sessions, monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_FILTER", "all")
    with sync_sessions() as db:
        ok, _ = should_publish(db, _trip(uuid.uuid4()))
    assert ok is True


def test_unknown_mode_falls_back_to_interesting(sync_sessions, monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_FILTER", "banana")
    with sync_sessions() as db:
        ok, reason = should_publish(db, _trip(uuid.uuid4()))
    assert "corridor" in reason


def test_rare_corridor_is_published(sync_sessions, monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_FILTER", "interesting")
    corridor = f"Rare-{uuid.uuid4().hex[:8]}"
    with sync_sessions() as db:
        ok, reason = should_publish(db, _trip(uuid.uuid4(), destination=corridor))
    assert ok is True
    assert "rare corridor" in reason


def test_busy_corridor_is_skipped(sync_sessions, seed_carrier, monkeypatch):
    """Once a route is routine it stops being news — which is what keeps a
    single platform key from turning into a firehose."""
    monkeypatch.setenv("NOSTR_PUBLISH_FILTER", "interesting")
    monkeypatch.setenv("NOSTR_PUBLISH_RARE_CORRIDOR_MAX", "2")

    origin = f"O-{uuid.uuid4().hex[:6]}"
    destination = f"D-{uuid.uuid4().hex[:6]}"
    with sync_sessions() as db:
        for _ in range(3):
            db.add(_trip(seed_carrier.id, origin=origin, destination=destination))
        db.commit()
        ok, reason = should_publish(
            db, _trip(seed_carrier.id, origin=origin, destination=destination)
        )
    assert ok is False
    assert "common corridor" in reason
