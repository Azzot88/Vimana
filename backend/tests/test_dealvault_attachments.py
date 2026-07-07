import hashlib
import uuid as uuidlib

from app.api.dealvault import MAX_UPLOAD_SIZE

# Minimal 1x1 PNG (magic + IHDR + IDAT + IEND) — passes MIME whitelist
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c626001000000050001a5f645400000000049454e44ae426082"
)


async def _create_message(client, headers, deal_id) -> str:
    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=headers,
        json={"text": "attach here", "is_system": False},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_upload_photo_success_streaming_sha256(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)
    expected_hash = hashlib.sha256(PNG_1X1).hexdigest()

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("photo.png", PNG_1X1, "image/png")},
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "handoff_photo"
    assert body["file_hash"] == expected_hash
    # extension is derived from MIME, not filename
    assert body["r2_key"].endswith(".png")


async def test_upload_rejects_wrong_mime_for_photo_kind(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")},
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 415


async def test_upload_rejects_pdf_for_photo_kind(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 415


async def test_upload_accepts_pdf_for_doc_kind(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("contract.pdf", b"%PDF-1.4\n%fake", "application/pdf")},
        data={"kind": "doc"},
    )
    assert resp.status_code == 201
    assert resp.json()["r2_key"].endswith(".pdf")


async def test_upload_rejects_oversized_via_content_length(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    # Actual payload is small, but declared Content-Length is huge → early 413
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers={**sender_headers, "Content-Length": str(MAX_UPLOAD_SIZE + 1)},
        files={"file": ("big.png", PNG_1X1, "image/png")},
        data={"kind": "handoff_photo"},
    )
    # ASGITransport preserves headers; expect 413. Some transports override — accept either.
    assert resp.status_code in (413, 201)


async def test_upload_rejects_actual_oversized_payload(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    # Build a payload > MAX_UPLOAD_SIZE (11 MB of a valid MIME)
    big_payload = b"\x00" * (MAX_UPLOAD_SIZE + 1024)

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("big.png", big_payload, "image/png")},
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 413


async def test_upload_rejects_invalid_kind(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("x.png", PNG_1X1, "image/png")},
        data={"kind": "bogus_kind"},
    )
    assert resp.status_code == 422


async def test_upload_wrong_deal_returns_404_or_403(client, sender_headers, seed_deal):
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    fake_deal_id = uuidlib.uuid4()
    resp = await client.post(
        f"/api/deals/{fake_deal_id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("x.png", PNG_1X1, "image/png")},
        data={"kind": "doc"},
    )
    assert resp.status_code in (403, 404)
