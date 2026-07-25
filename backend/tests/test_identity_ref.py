"""T3.9 — Identity ↔ Deal intersection.

A document verified inside a deal must land in BOTH vaults: the canonical
encrypted `IdentityContainer` (owner-only) and a participant-visible copy in
the deal (`identity_doc` attachment on a system message), tied together by an
`identity_ref` chain entry whose `doc_hash` matches all three places.
"""
import hashlib
import uuid as uuidlib

from sqlalchemy import select, text

from app.core.deal_chain import verify_chain, verify_content
from app.models.deal import Attachment, DealEvent, DealEventType, DealVaultMessage
from app.models.verification import IdentityContainer
from tests.test_dealvault_attachments import PNG_1X1
from tests.test_verification import _make_active_deal, _upload_form


async def _verified_deal(client, carrier_headers, sender_headers) -> tuple[str, dict]:
    """Deal + carrier requests sender's ID + sender submits a document.
    Returns (deal_id, badge json)."""
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    assert req.status_code == 201, req.text
    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req.json()['id']}/submit-document",
        headers=sender_headers,
        data=_upload_form(),
        files={"file": ("passport.png", PNG_1X1, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return deal_id, resp.json()


async def _one_event(session_maker, deal_id, event_type) -> DealEvent:
    async with session_maker() as db:
        events = (
            (
                await db.execute(
                    select(DealEvent).where(
                        DealEvent.deal_id == uuidlib.UUID(str(deal_id)),
                        DealEvent.event_type == event_type,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 1, f"expected exactly one {event_type}, got {len(events)}"
    return events[0]


async def test_document_lands_in_both_vaults_with_triple_hash_match(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id, badge = await _verified_deal(client, carrier_headers, sender_headers)
    expected_hash = hashlib.sha256(PNG_1X1).hexdigest()

    ref = await _one_event(session_maker, deal_id, DealEventType.identity_ref)
    payload = ref.payload
    assert payload["doc_hash"] == expected_hash
    assert payload["badge_id"] == badge["id"]
    assert payload["doc_type"] == "passport"
    assert payload["doc_country"] == "AE"

    async with session_maker() as db:
        att = await db.get(Attachment, uuidlib.UUID(payload["attachment_id"]))
        cont = await db.get(IdentityContainer, uuidlib.UUID(payload["container_id"]))
        msg = await db.get(DealVaultMessage, uuidlib.UUID(str(att.message_id)))
        chain = await verify_chain(db, uuidlib.UUID(str(deal_id)))
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))

    # Triple match: chain payload == deal copy == canonical container.
    assert att.file_hash == expected_hash
    assert att.kind.value == "identity_doc"
    assert cont.doc_hash == expected_hash
    # The copy rides on a system message, chained like any vault content.
    assert msg.is_system is True
    assert msg.deal_id == uuidlib.UUID(str(deal_id))
    assert chain["ok"] is True
    assert content["content_ok"] is True
    assert content["checked_identity"] == 1


async def test_message_and_file_events_accompany_identity_ref(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id, _ = await _verified_deal(client, carrier_headers, sender_headers)
    file_evt = await _one_event(session_maker, deal_id, DealEventType.file_added)
    assert file_evt.payload["kind"] == "identity_doc"
    msg_evts = None
    async with session_maker() as db:
        msg_evts = (
            (
                await db.execute(
                    select(DealEvent).where(
                        DealEvent.deal_id == uuidlib.UUID(str(deal_id)),
                        DealEvent.event_type == DealEventType.message_added,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(msg_evts) == 1  # the system message about the verified document


async def test_swapped_identity_copy_is_detected(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id, _ = await _verified_deal(client, carrier_headers, sender_headers)
    ref = await _one_event(session_maker, deal_id, DealEventType.identity_ref)

    async with session_maker() as db:
        await db.execute(
            text("UPDATE attachments SET file_hash = :h WHERE id = :id"),
            {"h": "0" * 64, "id": uuidlib.UUID(ref.payload["attachment_id"])},
        )
        await db.commit()

    async with session_maker() as db:
        chain = await verify_chain(db, uuidlib.UUID(str(deal_id)))
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert chain["ok"] is True  # chain intact — content layer catches it
    assert content["content_ok"] is False
    reasons = {m["reason"] for m in content["mismatches"]}
    assert "identity copy hash mismatch" in reasons
    # file_added points at the same attachment → double detection.
    assert "file hash mismatch" in reasons


async def test_deleted_container_is_detected(
    client, session_maker, carrier_headers, sender_headers
):
    deal_id, _ = await _verified_deal(client, carrier_headers, sender_headers)
    ref = await _one_event(session_maker, deal_id, DealEventType.identity_ref)

    async with session_maker() as db:
        # Badge references the container — detach it first, then delete.
        await db.execute(
            text("UPDATE verification_badges SET container_ref_id = NULL WHERE container_ref_id = :id"),
            {"id": uuidlib.UUID(ref.payload["container_id"])},
        )
        await db.execute(
            text("DELETE FROM identity_containers WHERE id = :id"),
            {"id": uuidlib.UUID(ref.payload["container_id"])},
        )
        await db.commit()

    async with session_maker() as db:
        content = await verify_content(db, uuidlib.UUID(str(deal_id)))
    assert content["content_ok"] is False
    assert any(m["reason"] == "identity container missing" for m in content["mismatches"])


async def test_self_upload_creates_no_chain_events(
    client, session_maker, sender_headers, seed_sender
):
    before = None
    async with session_maker() as db:
        before = (
            await db.execute(
                text(
                    "SELECT count(*) FROM deal_events WHERE event_type = 'identity_ref'"
                )
            )
        ).scalar_one()

    resp = await client.post(
        "/api/me/verification/self-upload",
        headers=sender_headers,
        data=_upload_form(),
        files={"file": ("id.png", PNG_1X1, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["in_deal_id"] is None

    async with session_maker() as db:
        after = (
            await db.execute(
                text(
                    "SELECT count(*) FROM deal_events WHERE event_type = 'identity_ref'"
                )
            )
        ).scalar_one()
    assert after == before  # no deal — nothing to chain


async def test_identity_doc_kind_rejected_on_generic_upload(
    client, sender_headers, seed_deal
):
    """The copy is created only by the verification flow — manually uploading
    kind=identity_doc through the chat endpoint must not work."""
    msg = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "sneaky", "is_system": False},
    )
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg.json()['id']}/attachments",
        headers=sender_headers,
        files={"file": ("id.png", PNG_1X1, "image/png")},
        data={"kind": "identity_doc"},
    )
    assert resp.status_code == 415  # no MIME whitelist entry for this kind
