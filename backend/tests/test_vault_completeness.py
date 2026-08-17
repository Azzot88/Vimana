"""T3.7 — vault-content chain: message_added / file_added / sealed + coverage.

The T3.6 chain covered only status events; these tests prove the chain now
covers the content the vault exists for: messages and files are chained in the
same transaction as their rows, closing seals the vault, a dispute unseals it,
and `verify_content` catches deleted or swapped content that the (intact)
chain alone cannot see.
"""
import hashlib
import uuid as uuidlib
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import select, text

from app.core.deal_chain import content_hash_of, verify_chain, verify_content
from app.models.deal import Deal, DealEvent, DealEventType, DealVaultMessage
from app.models.user import User
from tests.conftest import SEED_PASSWORD, _login, make_account, unique_email

# Valid 1x1 PNG — built programmatically there (T3.8 decode validation).
from tests.test_dealvault_attachments import PNG_1X1


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


async def _fresh_deal(client, carrier_headers, sender_headers, origin="VLT", destination="CMP") -> str:
    """A brand-new deal via the API (never the shared seed_deal — several tests
    below seal the vault, which must not leak into other suites)."""
    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": origin,
            "destination": destination,
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    assert trip.status_code == 201, trip.text
    match = await client.post(
        "/api/deals/match",
        headers=sender_headers,
        json={
            "trip_id": trip.json()["id"],
            "order": {
                "recipient_contact": "+10000000042",
                "origin": origin,
                "destination": destination,
                "category": "document",
                "declared_value": 100.0,
            },
        },
    )
    assert match.status_code == 201, match.text
    return match.json()["id"]


async def _post_message(client, headers, deal_id, text_="vault message") -> dict:
    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=headers,
        json={"text": text_, "is_system": False},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _events_of(session_maker, deal_id, event_type: DealEventType) -> list[DealEvent]:
    async with session_maker() as db:
        return (
            (
                await db.execute(
                    select(DealEvent)
                    .where(
                        DealEvent.deal_id == uuidlib.UUID(str(deal_id)),
                        DealEvent.event_type == event_type,
                    )
                    .order_by(DealEvent.seq.asc())
                )
            )
            .scalars()
            .all()
        )


@pytest_asyncio.fixture
async def arbiter_user(client, session_maker):
    email = unique_email("vault-arbiter")
    reg = await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Vault Arbiter"},
    )
    assert reg.status_code == 201
    user_id = uuidlib.UUID(reg.json()["id"])
    async with session_maker() as db:
        u = await db.get(User, user_id)
        u.role = "arbiter"
        await db.commit()
    token = await _login(client, email)
    return {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}


# ─────────────────────────────────────────────────────────────
# 1. Messages and files are chained
# ─────────────────────────────────────────────────────────────


async def test_message_added_is_chained_and_content_verifies(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    msg = await _post_message(client, sender_headers, deal_id)

    events = await _events_of(session_maker, deal_id, DealEventType.message_added)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["message_id"] == msg["id"]
    assert payload["is_e2e"] is False
    assert payload["msg_event_id"] == msg["nostr_event_id"]

    async with session_maker() as db:
        row = await db.get(DealVaultMessage, uuidlib.UUID(msg["id"]))
        assert payload["content_hash"] == content_hash_of(
            row.text_ciphertext, row.text_nonce
        )
        chain = await verify_chain(db, uuidlib.UUID(str(deal_id)))
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert chain["ok"] is True
    assert content["content_ok"] is True
    assert content["checked_messages"] == 1


async def test_file_added_is_chained_with_file_hash(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    msg = await _post_message(client, sender_headers, deal_id)

    up = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg['id']}/attachments",
        headers=sender_headers,
        files={"file": ("photo.png", PNG_1X1, "image/png")},
        data={"kind": "handoff_photo"},
    )
    assert up.status_code == 201, up.text

    events = await _events_of(session_maker, deal_id, DealEventType.file_added)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["attachment_id"] == up.json()["id"]
    assert payload["file_hash"] == hashlib.sha256(PNG_1X1).hexdigest()
    assert payload["kind"] == "handoff_photo"
    assert payload["size_bytes"] == len(PNG_1X1)

    async with session_maker() as db:
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert content["content_ok"] is True
    assert content["checked_files"] == 1


# ─────────────────────────────────────────────────────────────
# 2. Tampering with content is detected even though the chain is intact
# ─────────────────────────────────────────────────────────────


async def test_swapped_ciphertext_is_detected(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    msg = await _post_message(client, sender_headers, deal_id, "original text")

    async with session_maker() as db:
        await db.execute(
            text(
                "UPDATE deal_vault_messages SET text_ciphertext = :ct WHERE id = :id"
            ),
            {"ct": b"tampered-bytes", "id": uuidlib.UUID(msg["id"])},
        )
        await db.commit()

    async with session_maker() as db:
        chain = await verify_chain(db, uuidlib.UUID(str(deal_id)))
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    # The chain itself still verifies — content verification is the layer
    # that catches the swap. Two independent claims, deliberately.
    assert chain["ok"] is True
    assert content["content_ok"] is False
    assert content["mismatches"][0]["reason"] == "content hash mismatch"

    resp = await client.get(f"/api/deals/{deal_id}/chain", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_ok"] is False
    assert body["content_mismatches"][0]["kind"] == "message"


async def test_deleted_message_is_detected(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    msg = await _post_message(client, sender_headers, deal_id)

    async with session_maker() as db:
        await db.execute(
            text("DELETE FROM deal_vault_messages WHERE id = :id"),
            {"id": uuidlib.UUID(msg["id"])},
        )
        await db.commit()

    async with session_maker() as db:
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert content["content_ok"] is False
    assert content["mismatches"][0]["reason"] == "message missing"


async def test_unreadable_reference_reads_as_missing_not_as_a_crash(
    client, session_maker, carrier_headers, sender_headers
):
    """A chain payload whose `message_id` is not a UUID at all.

    We write those ids ourselves, so this only happens to a corrupted row — and
    a corrupted row is precisely what this function exists to report. Before
    T_PERF.1 the id went straight into `uuid.UUID(...)` per event, so the
    endpoint answered 500 and said nothing about which entry was wrong.
    """
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    await _post_message(client, sender_headers, deal_id)

    async with session_maker() as db:
        await db.execute(
            text(
                "UPDATE deal_events SET payload = jsonb_set(payload::jsonb,"
                " '{message_id}', '\"not-a-uuid\"')::json"
                " WHERE deal_id = :deal AND event_type = 'message_added'"
            ),
            {"deal": uuidlib.UUID(str(deal_id))},
        )
        await db.commit()

    async with session_maker() as db:
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert content["content_ok"] is False
    assert content["mismatches"][0]["reason"] == "message missing"
    assert content["mismatches"][0]["ref_id"] == "not-a-uuid"

    resp = await client.get(f"/api/deals/{deal_id}/chain", headers=sender_headers)
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────
# 3. Sealing
# ─────────────────────────────────────────────────────────────


async def test_confirm_seals_the_vault(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    msg = await _post_message(client, sender_headers, deal_id)

    resp = await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    assert resp.status_code == 200, resp.text

    sealed_events = await _events_of(session_maker, deal_id, DealEventType.sealed)
    assert len(sealed_events) == 1
    assert sealed_events[0].payload["message_count"] == 1

    async with session_maker() as db:
        deal = await db.get(Deal, uuidlib.UUID(str(deal_id)))
        assert deal.sealed_at is not None

    # Content appends are refused with 409 across every surface.
    blocked_msg = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "after seal", "is_system": False},
    )
    assert blocked_msg.status_code == 409

    blocked_file = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg['id']}/attachments",
        headers=sender_headers,
        files={"file": ("late.png", PNG_1X1, "image/png")},
        data={"kind": "handoff_photo"},
    )
    assert blocked_file.status_code == 409

    blocked_event = await client.post(
        f"/api/deals/{deal_id}/event",
        headers=sender_headers,
        json={"event_type": "in_transit"},
    )
    assert blocked_event.status_code == 409

    blocked_share = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/share-address",
        headers=sender_headers,
        json={},
    )
    assert blocked_share.status_code == 409


async def test_dispute_unseals_and_closing_verdict_reseals(
    client, session_maker, carrier_headers, sender_headers, arbiter_user
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    await _post_message(client, sender_headers, deal_id)
    assert (
        await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    ).status_code == 200

    # Dispute after close is allowed and unseals the vault.
    dispute = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "item damaged, noticed after confirm"},
    )
    assert dispute.status_code == 201, dispute.text
    async with session_maker() as db:
        deal = await db.get(Deal, uuidlib.UUID(str(deal_id)))
        assert deal.sealed_at is None

    # Evidence can be appended again while disputed.
    evidence = await _post_message(client, sender_headers, deal_id, "photo of damage")
    assert evidence["id"]

    # Arbiter claims and resolves with a closing verdict → re-sealed.
    dispute_id = dispute.json()["id"]
    assert (
        await client.post(
            f"/api/disputes/{dispute_id}/claim", headers=arbiter_user["headers"]
        )
    ).status_code == 200
    resolve = await client.post(
        f"/api/disputes/{dispute_id}/resolve",
        headers=arbiter_user["headers"],
        json={"verdict": "carrier compensates", "closes_deal": True},
    )
    assert resolve.status_code == 200, resolve.text

    sealed_events = await _events_of(session_maker, deal_id, DealEventType.sealed)
    assert len(sealed_events) == 2  # confirm-seal + verdict-reseal
    async with session_maker() as db:
        deal = await db.get(Deal, uuidlib.UUID(str(deal_id)))
        assert deal.sealed_at is not None
        chain = await verify_chain(db, uuidlib.UUID(str(deal_id)))
    assert chain["ok"] is True


async def test_arbiter_read_of_sealed_vault_is_audited_without_content(
    client, session_maker, carrier_headers, sender_headers, arbiter_user
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    await _post_message(client, sender_headers, deal_id)
    assert (
        await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    ).status_code == 200
    dispute = await client.post(
        f"/api/deals/{deal_id}/dispute",
        headers=sender_headers,
        json={"reason": "post-close problem"},
    )
    dispute_id = dispute.json()["id"]
    assert (
        await client.post(
            f"/api/disputes/{dispute_id}/claim", headers=arbiter_user["headers"]
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/disputes/{dispute_id}/resolve",
            headers=arbiter_user["headers"],
            json={"verdict": "no fault", "closes_deal": True},
        )
    ).status_code == 200

    async with session_maker() as db:
        before = (
            await db.execute(
                text("SELECT count(*) FROM deal_vault_messages WHERE deal_id = :d"),
                {"d": uuidlib.UUID(str(deal_id))},
            )
        ).scalar_one()

    # Reading a sealed vault works, is chained as arbiter_opened, and adds no
    # chat message (content frozen, audit trail not).
    read = await client.get(
        f"/api/admin/deals/{deal_id}/vault", headers=arbiter_user["headers"]
    )
    assert read.status_code == 200, read.text

    async with session_maker() as db:
        after = (
            await db.execute(
                text("SELECT count(*) FROM deal_vault_messages WHERE deal_id = :d"),
                {"d": uuidlib.UUID(str(deal_id))},
            )
        ).scalar_one()
        chain = await verify_chain(db, uuidlib.UUID(str(deal_id)))
    assert after == before
    assert chain["ok"] is True
    audits = await _events_of(session_maker, deal_id, DealEventType.arbiter_opened)
    assert len(audits) >= 1


# ─────────────────────────────────────────────────────────────
# 4. /chain endpoint coverage + anchor backend default
# ─────────────────────────────────────────────────────────────


async def test_chain_endpoint_reports_seal_and_coverage(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    msg = await _post_message(client, sender_headers, deal_id)
    up = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg['id']}/attachments",
        headers=sender_headers,
        files={"file": ("photo.png", PNG_1X1, "image/png")},
        data={"kind": "receipt_photo"},
    )
    assert up.status_code == 201
    assert (
        await client.post(f"/api/deals/{deal_id}/confirm", headers=sender_headers)
    ).status_code == 200

    resp = await client.get(f"/api/deals/{deal_id}/chain", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["sealed_at"] is not None
    # T3.39 — two, not one: sealing now leaves a `deal.sealed` card in the vault
    # so a party reading the chat sees the deal close instead of the
    # conversation simply stopping. It is chained like any other message, which
    # is the point — the closing row must be as tamper-evident as the rest.
    assert body["total_messages"] == 2
    assert body["chained_messages"] == 2
    assert body["total_files"] == 1
    assert body["chained_files"] == 1
    assert body["content_ok"] is True
    assert body["content_mismatches"] == []


async def test_pinned_route_note_is_chained(
    client, session_maker, carrier_headers, sender_headers, seed_sender
):
    # Flag a dedicated corridor, then match a deal on it — the pinned
    # system-message must be vault content like any other, i.e. chained.
    from app.models.notices import NoticeSeverity, RouteNote, RouteStatus

    origin, destination = "VNT", "CHD"
    async with session_maker() as db:
        db.add(
            RouteNote(
                origin_iso=origin,
                destination_iso=destination,
                status=RouteStatus.attention,
                severity=NoticeSeverity.info,
                headline="chain-pin corridor",
                active_from=datetime.now(timezone.utc) - timedelta(days=1),
                created_by=seed_sender.id,
            )
        )
        await db.commit()

    deal_id = await _fresh_deal(
        client, carrier_headers, sender_headers, origin=origin, destination=destination
    )

    events = await _events_of(session_maker, deal_id, DealEventType.message_added)
    assert len(events) == 1  # the pinned note, chained at match time
    async with session_maker() as db:
        row = await db.get(
            DealVaultMessage, uuidlib.UUID(events[0].payload["message_id"])
        )
        assert row is not None and row.is_system is True
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert content["content_ok"] is True


async def test_anchor_backend_defaults_to_nostr(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id = await _fresh_deal(client, carrier_headers, sender_headers)
    anchor_id = uuidlib.uuid4()
    async with session_maker() as db:
        # Raw insert without `backend` — the server default must fill it, so
        # pre-T3.7 writer code paths keep working unchanged.
        await db.execute(
            text(
                "INSERT INTO deal_chain_anchors "
                "(id, deal_id, seq, entry_hash, nostr_event_id, nostr_pubkey) "
                "VALUES (:id, :deal_id, 1, :h, :eid, :pk)"
            ),
            {
                "id": anchor_id,
                "deal_id": uuidlib.UUID(str(deal_id)),
                "h": b"\x11" * 32,
                "eid": "e" * 64,
                "pk": "p" * 64,
            },
        )
        await db.commit()
        backend = (
            await db.execute(
                text("SELECT backend FROM deal_chain_anchors WHERE id = :id"),
                {"id": anchor_id},
            )
        ).scalar_one()
    assert backend == "nostr"
