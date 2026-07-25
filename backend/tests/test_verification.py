"""T2.1 — peer identity verification MVP tests."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest


async def _make_active_deal(client, carrier_headers, sender_headers) -> str:
    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "origin": "VER",
            "destination": "IFY",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "capacity": 3.0,
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
                "recipient_contact": "+10000005000",
                "origin": "VER",
                "destination": "IFY",
                "category": "document",
                "declared_value": 100.0,
            },
        },
    )
    return match.json()["id"]


def _upload_form(kind: str = "passport", country: str = "AE") -> dict:
    return {"doc_type": kind, "doc_country": country}


def _fake_doc_bytes() -> bytes:
    # T3.8: document uploads are content-validated (signature + decode), so
    # the fixture must be a real image, not arbitrary bytes.
    from tests.test_dealvault_attachments import PNG_1X1
    return PNG_1X1


# ─────────────────────────────────────────────────────────────
# Create request + basic flow
# ─────────────────────────────────────────────────────────────


async def test_carrier_requests_sender_id(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    resp = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"
    assert resp.json()["target_role"] == "sender"


async def test_sender_can_request_carrier_id(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    resp = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=sender_headers,
        json={"target_role": "carrier"},
    )
    assert resp.status_code == 201


async def test_cannot_request_own_role(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    resp = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "carrier"},
    )
    assert resp.status_code == 422


async def test_outsider_cannot_request(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    email = unique_email("out")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "Out"},
    )
    token = await _login(client, email)
    outsider = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=outsider,
        json={"target_role": "sender"},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────
# Respond flows — asymmetric consequences
# ─────────────────────────────────────────────────────────────


async def test_sender_can_decline_hard(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    req_id = req.json()["id"]

    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/respond",
        headers=sender_headers,
        json={"action": "declined"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


async def test_carrier_cannot_use_hard_declined(client, carrier_headers, sender_headers):
    """`declined` is sender-only. Carrier must use `declined_polite`."""
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=sender_headers,
        json={"target_role": "carrier"},
    )
    req_id = req.json()["id"]

    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/respond",
        headers=carrier_headers,
        json={"action": "declined"},
    )
    assert resp.status_code == 422


async def test_carrier_polite_decline_no_consequence(
    client, carrier_headers, sender_headers
):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=sender_headers,
        json={"target_role": "carrier"},
    )
    req_id = req.json()["id"]

    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/respond",
        headers=carrier_headers,
        json={"action": "declined_polite"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined_polite"


async def test_later_in_person_response(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    req_id = req.json()["id"]

    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/respond",
        headers=sender_headers,
        json={"action": "later_in_person"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "later_in_person"


async def test_respond_by_non_target_forbidden(client, carrier_headers, sender_headers):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    req_id = req.json()["id"]

    # carrier tries to respond to a sender-targeted request
    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/respond",
        headers=carrier_headers,
        json={"action": "later_in_person"},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────
# Submit document + auto badge
# ─────────────────────────────────────────────────────────────


async def test_submit_document_creates_auto_badge(
    client, carrier_headers, sender_headers, seed_sender
):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    req_id = req.json()["id"]

    files = {"file": ("passport.jpg", _fake_doc_bytes(), "image/jpeg")}
    resp = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/submit-document",
        headers=sender_headers,
        data=_upload_form(),
        files=files,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["level"] == "auto"
    assert body["source"] == "auto_ocr"
    assert body["subject_id"] == str(seed_sender.id)


async def test_submit_document_updates_highest_level(
    client, carrier_headers, sender_headers, seed_sender
):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    req_id = req.json()["id"]

    files = {"file": ("id.jpg", _fake_doc_bytes(), "image/jpeg")}
    await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/submit-document",
        headers=sender_headers,
        data=_upload_form(),
        files=files,
    )
    summary = await client.get(f"/api/users/{seed_sender.id}/verifications")
    assert summary.status_code == 200
    assert summary.json()["highest_level"] == "auto"
    assert summary.json()["active_counts"]["auto"] >= 1


# ─────────────────────────────────────────────────────────────
# Escalate
# ─────────────────────────────────────────────────────────────


async def test_escalate_creates_dispute_and_marks_deal(
    client, carrier_headers, sender_headers, session_maker
):
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )
    req_id = req.json()["id"]

    esc = await client.post(
        f"/api/deals/{deal_id}/verification/{req_id}/escalate",
        headers=carrier_headers,
        json={"reason": "Passport photo does not match user"},
    )
    assert esc.status_code == 200
    assert esc.json()["status"] == "escalated"

    from app.models.deal import Deal, Dispute
    from sqlalchemy import select

    async with session_maker() as db:
        deal = await db.get(Deal, deal_id)
        assert deal.status.value == "disputed"
        dispute = (
            await db.execute(select(Dispute).where(Dispute.deal_id == deal_id))
        ).scalar_one_or_none()
        assert dispute is not None
        assert "identity_fraud" in dispute.reason


# ─────────────────────────────────────────────────────────────
# Self-upload
# ─────────────────────────────────────────────────────────────


async def test_self_upload_creates_badge_without_deal(
    client, sender_headers, seed_sender
):
    files = {"file": ("id.jpg", _fake_doc_bytes(), "image/jpeg")}
    resp = await client.post(
        "/api/me/verification/self-upload",
        headers=sender_headers,
        data=_upload_form(),
        files=files,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["level"] == "auto"
    assert body["in_deal_id"] is None


# ─────────────────────────────────────────────────────────────
# Public listing + revoke
# ─────────────────────────────────────────────────────────────


async def test_public_verifications_endpoint_no_blob(client, sender_headers, seed_sender):
    files = {"file": ("id.jpg", _fake_doc_bytes(), "image/jpeg")}
    await client.post(
        "/api/me/verification/self-upload",
        headers=sender_headers,
        data=_upload_form(),
        files=files,
    )
    summary = await client.get(f"/api/users/{seed_sender.id}/verifications")
    assert summary.status_code == 200
    body = summary.json()
    # Must NOT include container blob content in public API
    for b in body["badges"]:
        assert "blob_encrypted" not in b
        assert "doc_hash" not in b


async def test_subject_can_revoke_own_auto_badge(client, sender_headers, seed_sender):
    files = {"file": ("id.jpg", _fake_doc_bytes(), "image/jpeg")}
    up = await client.post(
        "/api/me/verification/self-upload",
        headers=sender_headers,
        data=_upload_form(),
        files=files,
    )
    badge_id = up.json()["id"]

    rev = await client.post(
        f"/api/verifications/{badge_id}/revoke", headers=sender_headers
    )
    assert rev.status_code == 200
    assert rev.json()["revoked_at"] is not None


# ─────────────────────────────────────────────────────────────
# Deal-scoped request listing — source for the sender banner (T2.1 pt.3)
# ─────────────────────────────────────────────────────────────


async def _polite_declined_deal(client, carrier_headers, sender_headers) -> str:
    """Sender asks for the carrier's ID, carrier politely declines."""
    deal_id = await _make_active_deal(client, carrier_headers, sender_headers)
    req = await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=sender_headers,
        json={"target_role": "carrier"},
    )
    await client.post(
        f"/api/deals/{deal_id}/verification/{req.json()['id']}/respond",
        headers=carrier_headers,
        json={"action": "declined_polite"},
    )
    return deal_id


async def test_list_requests_exposes_polite_decline_to_sender(
    client, carrier_headers, sender_headers
):
    """Exact predicate `<VerificationDeclineBanner>` depends on (DealPage.tsx).

    The status must reach the client as the raw `declined_polite` string —
    not a Python enum repr, not a translated label.
    """
    deal_id = await _polite_declined_deal(client, carrier_headers, sender_headers)

    resp = await client.get(
        f"/api/deals/{deal_id}/verification-requests", headers=sender_headers
    )
    assert resp.status_code == 200, resp.text
    matches = [
        r
        for r in resp.json()
        if r["status"] == "declined_polite" and r["target_role"] == "carrier"
    ]
    assert len(matches) == 1
    assert matches[0]["resolved_at"] is not None


async def test_list_requests_visible_to_both_participants(
    client, carrier_headers, sender_headers
):
    deal_id = await _polite_declined_deal(client, carrier_headers, sender_headers)

    as_carrier = await client.get(
        f"/api/deals/{deal_id}/verification-requests", headers=carrier_headers
    )
    assert as_carrier.status_code == 200
    assert [r["status"] for r in as_carrier.json()] == ["declined_polite"]


async def test_list_requests_newest_first(client, carrier_headers, sender_headers):
    deal_id = await _polite_declined_deal(client, carrier_headers, sender_headers)
    await client.post(
        f"/api/deals/{deal_id}/verification",
        headers=carrier_headers,
        json={"target_role": "sender"},
    )

    resp = await client.get(
        f"/api/deals/{deal_id}/verification-requests", headers=sender_headers
    )
    rows = resp.json()
    assert len(rows) == 2
    stamps = [r["created_at"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)


async def test_list_requests_outsider_forbidden(
    client, carrier_headers, sender_headers
):
    deal_id = await _polite_declined_deal(client, carrier_headers, sender_headers)
    from tests.conftest import SEED_PASSWORD, _login, unique_email

    email = unique_email("nosy")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "Nosy"},
    )
    token = await _login(client, email)

    resp = await client.get(
        f"/api/deals/{deal_id}/verification-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_list_requests_unknown_deal_404(client, sender_headers):
    resp = await client.get(
        f"/api/deals/{uuid.uuid4()}/verification-requests", headers=sender_headers
    )
    assert resp.status_code == 404
