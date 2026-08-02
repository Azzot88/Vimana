"""T3.6 — hash chain over deal_events + Nostr anchoring.

Split in three: the hash primitive (pure), the append/verify path (async, real
DB), and the anchoring layer (sync session, because the Celery path bridges
`asyncio.run` and cannot be driven from inside a running loop).
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import chain_anchor
from app.core.chain_anchor import (
    NOSTR_KIND_CHAIN_ANCHOR,
    anchor_deal_head,
    build_anchor_event,
    find_unanchored_heads,
    is_anchoring_enabled,
)
from app.core.deal_chain import (
    GENESIS_HASH,
    ChainError,
    append_deal_event,
    canonical_json,
    compute_entry_hash,
    hash_of,
    head_of,
    verify_chain,
)
from app.core.keypair import generate_keypair, npub_from_nsec, verify_event_id
from app.core.signing import compute_event_id
from app.models.deal import Deal, DealChainAnchor, DealEvent, DealEventType, DealStatus
from app.models.marketplace import Order, OrderStatus
from tests.conftest import TEST_DATABASE_URL, unique_email

# `asyncio_mode = auto` (pytest.ini) — async defs run as asyncio tests, sync defs
# stay sync. The anchoring tests below rely on that: they must NOT run inside a
# loop, because the Celery path calls `asyncio.run`.

# That same `asyncio.run` builds a loop inside the test and closes it, out of
# reach of the autouse Redis teardown in conftest — so a client bound to it is
# finalised after its loop is gone. Handled centrally by
# `_silence_dead_loop_finalizers` in conftest; no blanket suppression here.


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


async def _fresh_deal(session_maker, seed_trip, seed_sender, seed_carrier) -> Deal:
    """A deal with an empty chain, isolated from other tests."""
    async with session_maker() as db:
        order = Order(
            sender_id=seed_sender.id,
            recipient_contact="+10000000001",
            origin=seed_trip.origin,
            destination=seed_trip.destination,
            category="document",
            declared_value=50.0,
            currency="USD",
            description="chain test order",
            status=OrderStatus.matched,
            trip_id=seed_trip.id,
        )
        db.add(order)
        await db.flush()
        deal = Deal(
            order_id=order.id,
            trip_id=seed_trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.matched,
        )
        db.add(deal)
        await db.commit()
        await db.refresh(deal)
        return deal


@pytest_asyncio.fixture
async def chain_deal(session_maker, seed_trip, seed_sender, seed_carrier) -> Deal:
    return await _fresh_deal(session_maker, seed_trip, seed_sender, seed_carrier)


# ─────────────────────────────────────────────────────────────
# 1. Hash primitive
# ─────────────────────────────────────────────────────────────


def _base_kwargs(**over):
    kwargs = dict(
        deal_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        seq=1,
        timestamp=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
        event_type=DealEventType.created,
        actor_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        nostr_event_id="a" * 64,
        payload={"b": 1, "a": 2},
        prev_hash=None,
    )
    kwargs.update(over)
    return kwargs


def test_hash_is_deterministic():
    assert compute_entry_hash(**_base_kwargs()) == compute_entry_hash(**_base_kwargs())
    assert len(compute_entry_hash(**_base_kwargs())) == 32


def test_hash_ignores_payload_key_order():
    """Canonical JSON sorts keys — the same mapping must hash identically
    regardless of how it was constructed."""
    a = compute_entry_hash(**_base_kwargs(payload={"a": 2, "b": 1}))
    b = compute_entry_hash(**_base_kwargs(payload={"b": 1, "a": 2}))
    assert a == b


@pytest.mark.parametrize(
    "field,value",
    [
        ("deal_id", uuid.UUID("33333333-3333-3333-3333-333333333333")),
        ("seq", 2),
        ("timestamp", datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc)),
        ("event_type", DealEventType.accepted),
        ("actor_id", uuid.UUID("44444444-4444-4444-4444-444444444444")),
        ("nostr_event_id", "b" * 64),
        ("payload", {"a": 2, "b": 2}),
        ("prev_hash", b"\x01" * 32),
    ],
)
def test_every_field_changes_the_hash(field, value):
    """No field may be decorative — if it is in the preimage it must move the hash."""
    assert compute_entry_hash(**_base_kwargs()) != compute_entry_hash(
        **_base_kwargs(**{field: value})
    )


def test_presence_byte_separates_none_from_zero_uuid():
    """Without a presence byte, `actor_id=None` and the zero UUID would collide."""
    none_hash = compute_entry_hash(**_base_kwargs(actor_id=None))
    zero_hash = compute_entry_hash(**_base_kwargs(actor_id=uuid.UUID(int=0)))
    assert none_hash != zero_hash


def test_presence_byte_separates_none_from_empty_nostr_id():
    assert compute_entry_hash(**_base_kwargs(nostr_event_id=None)) != compute_entry_hash(
        **_base_kwargs(nostr_event_id="")
    )


def test_genesis_is_hashed_for_first_entry():
    """prev_hash=None must hash exactly as 32 zero bytes."""
    assert compute_entry_hash(**_base_kwargs(prev_hash=None)) == compute_entry_hash(
        **_base_kwargs(prev_hash=GENESIS_HASH)
    )


def test_naive_timestamp_treated_as_utc():
    naive = datetime(2026, 7, 24, 12, 0, 0)
    aware = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert compute_entry_hash(**_base_kwargs(timestamp=naive)) == compute_entry_hash(
        **_base_kwargs(timestamp=aware)
    )


def test_non_serializable_payload_raises_not_silently_empty():
    """A payload that cannot be canonicalised must abort, never hash as `{}`."""
    with pytest.raises(ChainError):
        compute_entry_hash(**_base_kwargs(payload={"bad": object()}))


def test_canonical_json_sorts_and_strips_whitespace():
    assert canonical_json({"b": 1, "a": [1, {"d": 2, "c": 3}]}) == (
        '{"a":[1,{"c":3,"d":2}],"b":1}'
    )


def test_canonical_json_handles_none():
    assert canonical_json(None) == "null"


# ─────────────────────────────────────────────────────────────
# 2. Append + verify against a real DB
# ─────────────────────────────────────────────────────────────


async def test_first_entry_starts_at_seq_one_with_null_prev(
    session_maker, chain_deal, seed_sender
):
    async with session_maker() as db:
        evt = await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            payload={"x": 1},
            author=seed_sender,
        )
        await db.commit()

    assert evt.seq == 1
    assert evt.prev_hash is None
    assert bytes(evt.entry_hash) == hash_of(evt)


async def test_second_entry_links_to_first(session_maker, chain_deal, seed_sender):
    async with session_maker() as db:
        first = await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        second = await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.accepted,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        await db.commit()
        first_hash = bytes(first.entry_hash)

    assert second.seq == 2
    assert bytes(second.prev_hash) == first_hash


async def test_two_appends_in_one_transaction_chain_correctly(
    session_maker, chain_deal, seed_sender
):
    """The confirm→close path appends twice before commit; the second call must
    see the first as head even though nothing is committed yet."""
    async with session_maker() as db:
        a = await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.confirmed,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        b = await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.closed,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        a_hash = bytes(a.entry_hash)
        await db.commit()

    assert (a.seq, b.seq) == (1, 2)
    assert bytes(b.prev_hash) == a_hash


async def test_chains_are_independent_per_deal(
    session_maker, seed_trip, seed_sender, seed_carrier
):
    """seq restarts at 1 for each deal — a chain is scoped to its deal."""
    deal_a = await _fresh_deal(session_maker, seed_trip, seed_sender, seed_carrier)
    deal_b = await _fresh_deal(session_maker, seed_trip, seed_sender, seed_carrier)
    async with session_maker() as db:
        a = await append_deal_event(
            db,
            deal_id=deal_a.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        b = await append_deal_event(
            db,
            deal_id=deal_b.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        await db.commit()

    assert a.seq == 1 and b.seq == 1
    assert bytes(a.entry_hash) != bytes(b.entry_hash)


async def test_head_of_empty_chain_is_none(session_maker, chain_deal):
    async with session_maker() as db:
        assert await head_of(db, chain_deal.id) is None


async def test_verify_empty_chain_is_ok(session_maker, chain_deal):
    async with session_maker() as db:
        result = await verify_chain(db, chain_deal.id)
    assert result["ok"] is True
    assert result["length"] == 0
    assert result["head_seq"] is None


async def test_verify_intact_chain(session_maker, chain_deal, seed_sender):
    async with session_maker() as db:
        for i in range(5):
            await append_deal_event(
                db,
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                payload={"i": i},
                author=seed_sender,
            )
        await db.commit()
        result = await verify_chain(db, chain_deal.id)

    assert result["ok"] is True
    assert result["length"] == 5
    assert result["head_seq"] == 5
    assert result["broken_at"] is None
    assert len(result["head_hash"]) == 64


async def test_edited_payload_is_detected(session_maker, chain_deal, seed_sender):
    """The core claim: changing a stored event breaks verification at that entry."""
    async with session_maker() as db:
        for i in range(3):
            await append_deal_event(
                db,
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                payload={"i": i},
                author=seed_sender,
            )
        await db.commit()

    async with session_maker() as db:
        await db.execute(
            text(
                "UPDATE deal_events SET payload = '{\"i\": 99}'::json "
                "WHERE deal_id = :d AND seq = 2"
            ),
            {"d": str(chain_deal.id)},
        )
        await db.commit()
        result = await verify_chain(db, chain_deal.id)

    assert result["ok"] is False
    assert result["broken_at"] == 2
    assert "does not match stored hash" in result["reason"]


async def test_deleted_middle_entry_is_detected(
    session_maker, chain_deal, seed_sender
):
    """Deleting a row leaves a seq gap — the thing a plain signature cannot catch."""
    async with session_maker() as db:
        for i in range(3):
            await append_deal_event(
                db,
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                payload={"i": i},
                author=seed_sender,
            )
        await db.commit()

    async with session_maker() as db:
        await db.execute(
            delete(DealEvent).where(
                DealEvent.deal_id == chain_deal.id, DealEvent.seq == 2
            )
        )
        await db.commit()
        result = await verify_chain(db, chain_deal.id)

    assert result["ok"] is False
    assert result["broken_at"] == 3
    assert "expected seq 2" in result["reason"]


async def test_rewritten_prev_hash_is_detected(
    session_maker, chain_deal, seed_sender
):
    async with session_maker() as db:
        for i in range(3):
            await append_deal_event(
                db,
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                payload={"i": i},
                author=seed_sender,
            )
        await db.commit()

    async with session_maker() as db:
        await db.execute(
            text(
                "UPDATE deal_events SET prev_hash = decode(:h, 'hex') "
                "WHERE deal_id = :d AND seq = 3"
            ),
            {"h": "ff" * 32, "d": str(chain_deal.id)},
        )
        await db.commit()
        result = await verify_chain(db, chain_deal.id)

    assert result["ok"] is False
    assert result["broken_at"] == 3
    assert "prev_hash" in result["reason"]


async def test_truncating_the_tail_is_not_flagged(
    session_maker, chain_deal, seed_sender
):
    """Documents a real limit: dropping the newest entries leaves a chain that
    still verifies. Only external anchoring catches that — see the anchor tests."""
    async with session_maker() as db:
        for i in range(3):
            await append_deal_event(
                db,
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                payload={"i": i},
                author=seed_sender,
            )
        await db.commit()

    async with session_maker() as db:
        await db.execute(
            delete(DealEvent).where(
                DealEvent.deal_id == chain_deal.id, DealEvent.seq == 3
            )
        )
        await db.commit()
        result = await verify_chain(db, chain_deal.id)

    assert result["ok"] is True
    assert result["head_seq"] == 2


async def test_unchained_insert_is_rejected(session_maker, chain_deal, seed_sender):
    """The structural guard: a bare DealEvent cannot reach the table."""
    async with session_maker() as db:
        db.add(
            DealEvent(
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                payload=None,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


async def test_duplicate_seq_is_rejected(session_maker, chain_deal, seed_sender):
    async with session_maker() as db:
        evt = await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        await db.commit()
        entry_hash = bytes(evt.entry_hash)

    async with session_maker() as db:
        db.add(
            DealEvent(
                deal_id=chain_deal.id,
                event_type=DealEventType.accepted,
                actor_id=seed_sender.id,
                seq=1,
                entry_hash=entry_hash,
                timestamp=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


async def test_nostr_signature_is_bound_into_the_hash(
    session_maker, chain_deal, seed_sender
):
    """Swapping a signature must break the chain — the two mechanisms cannot be
    peeled apart."""
    async with session_maker() as db:
        await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        await db.commit()

    async with session_maker() as db:
        evt = (
            (
                await db.execute(
                    select(DealEvent).where(DealEvent.deal_id == chain_deal.id)
                )
            )
            .scalars()
            .one()
        )
        assert evt.nostr_event_id is not None  # custodial seed user → server-signed
        await db.execute(
            text(
                "UPDATE deal_events SET nostr_event_id = :e WHERE id = :i"
            ),
            {"e": "c" * 64, "i": str(evt.id)},
        )
        await db.commit()
        result = await verify_chain(db, chain_deal.id)

    assert result["ok"] is False
    assert result["broken_at"] == 1


# ─────────────────────────────────────────────────────────────
# 3. Chain through the real deal endpoints
# ─────────────────────────────────────────────────────────────


async def test_deal_lifecycle_produces_a_valid_chain(
    client, session_maker, sender_headers, carrier_headers
):
    """match → accept → handoff → confirm(+close) must leave a verifiable chain."""
    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "MTC",
            "destination": "DXB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201, trip.text

    resp = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000000002",
                "origin": "MTC",
                "destination": "DXB",
                "category": "document",
                "declared_value": 10.0,
                "description": "lifecycle chain",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    deal_id = resp.json()["id"]

    assert (
        await client.post(f"/api/deals/{deal_id}/accept", headers=carrier_headers)
    ).status_code == 200
    assert (
        await client.post(
            f"/api/deals/{deal_id}/event",
            headers=carrier_headers,
            json={"event_type": "handoff", "payload": {"note": "picked up"}},
        )
    ).status_code == 200
    assert (
        await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    ).status_code == 200

    async with session_maker() as db:
        result = await verify_chain(db, uuid.UUID(deal_id))

    # created, accepted, handoff, confirmed, closed + sealed (T3.7)
    assert result["ok"] is True
    assert result["length"] == 6
    assert [1, 2, 3, 4, 5, 6] == list(range(1, result["head_seq"] + 1))


async def test_chain_endpoint_reports_status(
    client, session_maker, sender_headers, chain_deal, seed_sender
):
    async with session_maker() as db:
        await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.created,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        await db.commit()

    resp = await client.get(f"/api/deals/{chain_deal.id}/chain", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["length"] == 1
    assert body["head_seq"] == 1
    assert len(body["head_hash"]) == 64
    # Nothing anchored yet — the two claims are reported independently.
    assert body["anchored_seq"] is None
    assert body["anchor_event_id"] is None


async def test_chain_endpoint_rejects_outsider(client, chain_deal):
    email = unique_email("chain-outsider")
    reg = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "outsider-pass-123",
            "display_name": "Outsider",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": "outsider-pass-123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/deals/{chain_deal.id}/chain", headers=headers)
    assert resp.status_code == 403


async def test_chain_endpoint_404_for_unknown_deal(client, sender_headers):
    resp = await client.get(
        f"/api/deals/{uuid.uuid4()}/chain", headers=sender_headers
    )
    assert resp.status_code == 404


async def test_chain_endpoint_requires_auth(client, chain_deal):
    assert (await client.get(f"/api/deals/{chain_deal.id}/chain")).status_code == 401


# ─────────────────────────────────────────────────────────────
# 4. Anchoring
# ─────────────────────────────────────────────────────────────


def test_anchor_event_is_well_formed_and_verifies():
    nsec_hex, npub_hex = generate_keypair()
    deal_id = uuid.uuid4()
    head_hash = "ab" * 32

    event = build_anchor_event(
        deal_id=deal_id, seq=7, entry_hash_hex=head_hash, nsec_hex=nsec_hex
    )

    assert event["kind"] == NOSTR_KIND_CHAIN_ANCHOR
    assert event["pubkey"] == npub_hex == npub_from_nsec(nsec_hex)
    tags = {t[0]: t[1] for t in event["tags"]}
    assert tags["deal"] == str(deal_id)
    assert tags["seq"] == "7"
    assert tags["h"] == head_hash
    # id must be the NIP-01 id of exactly these fields, and the sig must verify.
    assert event["id"] == compute_event_id(
        event["pubkey"],
        event["created_at"],
        event["kind"],
        event["tags"],
        event["content"],
    )
    assert verify_event_id(event["id"], event["sig"], event["pubkey"])


def test_anchor_content_carries_the_head():
    nsec_hex, _ = generate_keypair()
    deal_id = uuid.uuid4()
    event = build_anchor_event(
        deal_id=deal_id, seq=3, entry_hash_hex="cd" * 32, nsec_hex=nsec_hex
    )
    body = json.loads(event["content"])
    assert body == {
        "deal_id": str(deal_id),
        "seq": 3,
        "entry_hash": "cd" * 32,
        "alg": "sha256-chain-v1",
    }


def test_anchoring_disabled_without_key(monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_ENABLED", "true")
    monkeypatch.delenv("CHAIN_ANCHOR_NSEC", raising=False)
    assert is_anchoring_enabled() is False


def test_anchoring_disabled_when_publish_off(monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_ENABLED", "false")
    monkeypatch.setenv("CHAIN_ANCHOR_NSEC", generate_keypair()[0])
    assert is_anchoring_enabled() is False


def test_anchoring_enabled_when_both_set(monkeypatch):
    monkeypatch.setenv("NOSTR_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("CHAIN_ANCHOR_NSEC", generate_keypair()[0])
    assert is_anchoring_enabled() is True


# The Celery path is sync and bridges `asyncio.run`, so these run on a sync
# session against the same test database.


@pytest.fixture
def sync_session():
    url = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_sync_chain(db: Session, n: int = 2) -> tuple[uuid.UUID, bytes]:
    """Build a deal with `n` chained events using a sync session."""
    seed = db.execute(select(Deal).limit(1)).scalars().first()
    if seed is None:
        # Only happens when this file is run in isolation with `-k anchor`; the
        # async tests above create deals in definition order during a full run.
        pytest.skip("no deal in the test DB — run the full module")

    order = Order(
        sender_id=seed.sender_id,
        recipient_contact="+10000000003",
        origin="AAA",
        destination="BBB",
        category="document",
        declared_value=10.0,
        currency="USD",
        description="anchor test",
        status=OrderStatus.matched,
        trip_id=seed.trip_id,
    )
    db.add(order)
    db.flush()
    deal = Deal(
        order_id=order.id,
        trip_id=seed.trip_id,
        sender_id=seed.sender_id,
        carrier_id=seed.carrier_id,
        status=DealStatus.matched,
    )
    db.add(deal)
    db.flush()

    prev = None
    base = datetime.now(timezone.utc)
    for i in range(1, n + 1):
        ts = base + timedelta(seconds=i)
        entry_hash = compute_entry_hash(
            deal_id=deal.id,
            seq=i,
            timestamp=ts,
            event_type=DealEventType.handoff,
            actor_id=seed.sender_id,
            nostr_event_id=None,
            payload={"i": i},
            prev_hash=prev,
        )
        db.add(
            DealEvent(
                deal_id=deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed.sender_id,
                payload={"i": i},
                timestamp=ts,
                seq=i,
                entry_hash=entry_hash,
                prev_hash=prev,
            )
        )
        prev = entry_hash
    db.commit()
    return deal.id, prev


def test_find_unanchored_heads_includes_never_anchored(sync_session):
    deal_id, _ = _seed_sync_chain(sync_session, n=2)
    heads = dict(find_unanchored_heads(sync_session, limit=1000))
    assert heads.get(deal_id) == 2


def test_anchor_writes_row_and_matches_chain_head(sync_session, monkeypatch):
    deal_id, head_hash = _seed_sync_chain(sync_session, n=3)
    nsec_hex, _ = generate_keypair()

    async def _fake_publish(event):
        return {"wss://relay.example": True, "wss://own.example": True}

    monkeypatch.setattr(chain_anchor, "publish_event", _fake_publish)

    result = anchor_deal_head(sync_session, deal_id, 3, nsec_hex)
    assert result["published"] is True

    anchor = (
        sync_session.execute(
            select(DealChainAnchor).where(DealChainAnchor.deal_id == deal_id)
        )
        .scalars()
        .one()
    )
    assert anchor.seq == 3
    # The anchored hash must be the actual chain head, not a recomputation.
    assert bytes(anchor.entry_hash) == head_hash
    assert anchor.nostr_event_id == result["event_id"]
    assert anchor.relays == {"wss://relay.example": True, "wss://own.example": True}

    # Head is now covered — nothing left to anchor for this deal.
    assert deal_id not in dict(find_unanchored_heads(sync_session, limit=1000))


def test_anchor_not_recorded_when_every_relay_rejects(sync_session, monkeypatch):
    """No row on failure, so the same head is retried next tick."""
    deal_id, _ = _seed_sync_chain(sync_session, n=1)
    nsec_hex, _ = generate_keypair()

    async def _fake_publish(event):
        return {"wss://relay.example": False}

    monkeypatch.setattr(chain_anchor, "publish_event", _fake_publish)

    result = anchor_deal_head(sync_session, deal_id, 1, nsec_hex)
    assert result["published"] is False
    assert (
        sync_session.execute(
            select(DealChainAnchor).where(DealChainAnchor.deal_id == deal_id)
        )
        .scalars()
        .first()
        is None
    )
    assert dict(find_unanchored_heads(sync_session, limit=1000)).get(deal_id) == 1


def test_growth_past_an_anchor_is_picked_up_again(sync_session, monkeypatch):
    deal_id, _ = _seed_sync_chain(sync_session, n=2)
    nsec_hex, _ = generate_keypair()

    async def _fake_publish(event):
        return {"wss://relay.example": True}

    monkeypatch.setattr(chain_anchor, "publish_event", _fake_publish)
    anchor_deal_head(sync_session, deal_id, 2, nsec_hex)
    assert deal_id not in dict(find_unanchored_heads(sync_session, limit=1000))

    # One more entry lands — head moves ahead of the anchor.
    deal = sync_session.get(Deal, deal_id)
    prev = bytes(
        sync_session.execute(
            select(DealEvent.entry_hash).where(
                DealEvent.deal_id == deal_id, DealEvent.seq == 2
            )
        )
        .scalars()
        .one()
    )
    ts = datetime.now(timezone.utc)
    entry_hash = compute_entry_hash(
        deal_id=deal_id,
        seq=3,
        timestamp=ts,
        event_type=DealEventType.closed,
        actor_id=deal.sender_id,
        nostr_event_id=None,
        payload=None,
        prev_hash=prev,
    )
    sync_session.add(
        DealEvent(
            deal_id=deal_id,
            event_type=DealEventType.closed,
            actor_id=deal.sender_id,
            payload=None,
            timestamp=ts,
            seq=3,
            entry_hash=entry_hash,
            prev_hash=prev,
        )
    )
    sync_session.commit()

    assert dict(find_unanchored_heads(sync_session, limit=1000)).get(deal_id) == 3


def test_anchor_skips_when_head_moved(sync_session, monkeypatch):
    """Racing the scan: the requested seq no longer exists → skip, retry later."""
    deal_id, _ = _seed_sync_chain(sync_session, n=1)
    nsec_hex, _ = generate_keypair()

    called = False

    async def _fake_publish(event):
        nonlocal called
        called = True
        return {"wss://relay.example": True}

    monkeypatch.setattr(chain_anchor, "publish_event", _fake_publish)
    result = anchor_deal_head(sync_session, deal_id, 99, nsec_hex)

    assert result["skipped"] == "head not found"
    assert called is False


# ─────────────────────────────────────────────────────────────
# 5. T3.20 — what the API is allowed to claim about an anchor
# ─────────────────────────────────────────────────────────────


async def test_chain_endpoint_says_where_to_check_and_how_far(
    client, session_maker, sender_headers, chain_deal, seed_sender, monkeypatch
):
    """An anchor is worth exactly the third parties holding it.

    So the endpoint reports *which* relays took the event — an auditor has to go
    somewhere — and reports our own relay separately, because a head that only
    landed on our strfry proves nothing about us. Relays that refused are not
    listed at all: sending someone to look for an event that is not there is
    worse than saying nothing.
    """
    monkeypatch.setenv("NOSTR_OWN_RELAY_URL", "ws://nostr-relay:7777")

    async with session_maker() as db:
        for _ in range(3):
            await append_deal_event(
                db,
                deal_id=chain_deal.id,
                event_type=DealEventType.handoff,
                actor_id=seed_sender.id,
                author=seed_sender,
            )
        await db.commit()

        head_seq, _ = await head_of(db, chain_deal.id)
        anchored_seq = head_seq - 1
        db.add(
            DealChainAnchor(
                deal_id=chain_deal.id,
                seq=anchored_seq,
                entry_hash=bytes(
                    (
                        await db.execute(
                            select(DealEvent.entry_hash).where(
                                DealEvent.deal_id == chain_deal.id,
                                DealEvent.seq == anchored_seq,
                            )
                        )
                    ).scalars().one()
                ),
                nostr_event_id="ab" * 32,
                nostr_pubkey="cd" * 32,
                relays={
                    "wss://relay.damus.io": True,
                    "ws://nostr-relay:7777": True,
                    "wss://refused.example": False,
                },
            )
        )
        await db.commit()

    try:
        body = (
            await client.get(
                f"/api/deals/{chain_deal.id}/chain", headers=sender_headers
            )
        ).json()

        assert body["anchored_seq"] == anchored_seq
        assert sorted(body["anchor_relays"]) == [
            "ws://nostr-relay:7777",
            "wss://relay.damus.io",
        ]
        # The one that refused is absent, and our own is excluded from the list
        # that carries evidential weight.
        assert body["anchor_third_party_relays"] == ["wss://relay.damus.io"]
        # The claim stops at the anchor: this is how far past it we are.
        assert body["unanchored_entries"] == 1
    finally:
        async with session_maker() as db:
            await db.execute(
                delete(DealChainAnchor).where(DealChainAnchor.deal_id == chain_deal.id)
            )
            await db.commit()


async def test_nothing_is_anchored_means_nothing_is_covered(
    client, session_maker, sender_headers, chain_deal, seed_sender
):
    """With no anchor, every entry is outside the third-party claim — reported
    as the whole length, not as zero. Zero would read as "all covered"."""
    async with session_maker() as db:
        await append_deal_event(
            db,
            deal_id=chain_deal.id,
            event_type=DealEventType.handoff,
            actor_id=seed_sender.id,
            author=seed_sender,
        )
        await db.commit()

    body = (
        await client.get(f"/api/deals/{chain_deal.id}/chain", headers=sender_headers)
    ).json()
    assert body["anchored_seq"] is None
    assert body["anchor_relays"] == []
    assert body["anchor_third_party_relays"] == []
    assert body["unanchored_entries"] == body["head_seq"]
