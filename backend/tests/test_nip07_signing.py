"""T2.2 pt.2 — NIP-01 event format + NIP-07 client-signing flow."""
from datetime import datetime, timedelta, timezone

import pytest
from tests.conftest import make_account


@pytest.fixture
async def _matched_deal(client):
    """Fresh custodial carrier + self-custody sender + matched deal id."""
    from tests.conftest import SEED_PASSWORD, unique_email

    c_email = unique_email("nc-c")
    await make_account({
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "NcC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "AAA",
            "destination": "BBB",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]

    s_email = unique_email("nc-s")
    await make_account({"email": s_email, "password": SEED_PASSWORD, "display_name": "NcS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}

    # T3.12 — one step instead of export-then-claim: the test generates the key,
    # proves possession, and the account becomes self-custody holding it.
    from tests.conftest import establish_identity

    keys = await establish_identity(client, s_headers)

    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000007777",
                "origin": "AAA",
                "destination": "BBB",
                "category": "document",
                "declared_value": 40.0,
            },
        },
    )
    assert match.status_code == 201, match.json()
    return {
        "sender_headers": s_headers,
        "carrier_headers": c_headers,
        "deal_id": match.json()["id"],
        "nsec_hex": keys["nsec_hex"],
        "npub_hex": keys["npub_hex"],
    }


def _now_unix() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def _sign(deal_id: str, text: str, is_system: bool, nsec_hex: str, npub_hex: str, ts: int):
    """Client-side sign — mirrors what NIP-07 window.nostr.signEvent would do."""
    from app.core.keypair import sign_event_id
    from app.core.signing import (
        NOSTR_KIND_VAULT_MESSAGE,
        compute_event_id,
    )

    tags = [["k", "vault_message"], ["deal", deal_id]]
    if is_system:
        tags.append(["system", "1"])
    content = text or ""
    event_id = compute_event_id(npub_hex, ts, NOSTR_KIND_VAULT_MESSAGE, tags, content)
    sig = sign_event_id(event_id, nsec_hex)
    return sig, event_id


async def test_self_custody_pre_signed_vault_message_accepted(client, _matched_deal):
    d = _matched_deal
    ts = _now_unix()
    sig, event_id = _sign(d["deal_id"], "hi from self-custody", False, d["nsec_hex"], d["npub_hex"], ts)

    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"text": "hi from self-custody", "nostr_sig": sig, "nostr_created_at": ts},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["nostr_sig"] == sig
    assert body["nostr_event_id"] == event_id
    assert body["nostr_created_at"] == ts
    assert body["nostr_pubkey"] == d["npub_hex"]


async def test_pre_signed_missing_created_at_rejected(client, _matched_deal):
    d = _matched_deal
    ts = _now_unix()
    sig, _ = _sign(d["deal_id"], "no ts", False, d["nsec_hex"], d["npub_hex"], ts)

    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"text": "no ts", "nostr_sig": sig},
    )
    assert resp.status_code == 422
    assert "nostr_created_at" in resp.json()["detail"].lower()


async def test_pre_signed_stale_created_at_rejected(client, _matched_deal):
    d = _matched_deal
    stale_ts = _now_unix() - 3600  # 1 hour old, way past ±5 min
    sig, _ = _sign(d["deal_id"], "stale", False, d["nsec_hex"], d["npub_hex"], stale_ts)

    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"text": "stale", "nostr_sig": sig, "nostr_created_at": stale_ts},
    )
    assert resp.status_code == 422
    assert "skew" in resp.json()["detail"].lower()


async def test_pre_signed_wrong_sig_rejected(client, _matched_deal):
    d = _matched_deal
    ts = _now_unix()

    # Sign a DIFFERENT text than the one posted — event_id mismatch.
    sig, _ = _sign(d["deal_id"], "genuine text", False, d["nsec_hex"], d["npub_hex"], ts)

    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"text": "tampered text", "nostr_sig": sig, "nostr_created_at": ts},
    )
    assert resp.status_code == 422
    assert "invalid" in resp.json()["detail"].lower()


async def test_custodial_writes_nip01_event_id(client):
    """Custodial user's vault message gets event_id populated (new format)."""
    from tests.conftest import SEED_PASSWORD, unique_email

    c_email = unique_email("nip-c")
    await make_account({
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "NipC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "NIP",
            "destination": "ONE",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]

    s_email = unique_email("nip-s")
    await make_account({"email": s_email, "password": SEED_PASSWORD, "display_name": "NipS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}
    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000006666",
                "origin": "NIP",
                "destination": "ONE",
                "category": "document",
                "declared_value": 40.0,
            },
        },
    )
    deal_id = match.json()["id"]

    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=s_headers,
        json={"text": "custodial nip-01"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["nostr_sig"] and len(body["nostr_sig"]) == 128
    assert body["nostr_event_id"] and len(body["nostr_event_id"]) == 64
    assert body["nostr_pubkey"] and len(body["nostr_pubkey"]) == 64
    assert isinstance(body["nostr_created_at"], int)


async def test_custodial_deal_event_signed_new_format(client, session_maker):
    """Deal state event (accept) — custodial → server signs with kind 4802."""
    from app.core.keypair import verify_event_id
    from app.core.signing import (
        NOSTR_KIND_DEAL_EVENT,
        _content_deal_event,
        _tags_deal_event,
        compute_event_id,
    )
    from app.models.deal import DealEvent
    from sqlalchemy import select
    from tests.conftest import SEED_PASSWORD, unique_email

    c_email = unique_email("de-c")
    await make_account({
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "DeC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "DE1",
            "destination": "DE2",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]

    s_email = unique_email("de-s")
    await make_account({"email": s_email, "password": SEED_PASSWORD, "display_name": "DeS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}
    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000005555",
                "origin": "DE1",
                "destination": "DE2",
                "category": "document",
                "declared_value": 40.0,
            },
        },
    )
    deal_id = match.json()["id"]

    # Fetch the created deal event and verify its NIP-01 sig.
    async with session_maker() as db:
        result = await db.execute(select(DealEvent).where(DealEvent.deal_id == deal_id))
        evt = result.scalars().first()
        assert evt is not None
        assert evt.nostr_sig and len(evt.nostr_sig) == 128
        assert evt.nostr_event_id and len(evt.nostr_event_id) == 64
        assert evt.nostr_pubkey and len(evt.nostr_pubkey) == 64
        assert isinstance(evt.nostr_created_at, int)

        # Recompute event_id and verify sig — end-to-end proof.
        expected_id = compute_event_id(
            evt.nostr_pubkey,
            evt.nostr_created_at,
            NOSTR_KIND_DEAL_EVENT,
            _tags_deal_event(evt),
            _content_deal_event(evt),
        )
        assert expected_id == evt.nostr_event_id
        assert verify_event_id(evt.nostr_event_id, evt.nostr_sig, evt.nostr_pubkey)


async def test_self_custody_deal_event_lenient(client, _matched_deal, session_maker):
    """Self-custody user matched deal → DealEvent stays unsigned (no NIP-07 for clicks)."""
    from sqlalchemy import select

    from app.models.deal import DealEvent

    d = _matched_deal
    async with session_maker() as db:
        result = await db.execute(
            select(DealEvent).where(DealEvent.deal_id == d["deal_id"])
        )
        evt = result.scalars().first()
        assert evt is not None
        assert evt.nostr_sig is None
        assert evt.nostr_event_id is None
