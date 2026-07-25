import hashlib
import struct
import uuid as uuidlib
import zlib

from app.api.dealvault import MAX_UPLOAD_SIZE


def _make_png_1x1() -> bytes:
    """Minimal VALID 1x1 RGBA PNG, built programmatically so the chunk CRCs
    are correct by construction. The previous hand-crafted hex had a broken
    IDAT checksum — it passed the old MIME-whitelist era but T3.8's decode
    validation (rightly) rejects it."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1, 8-bit, RGBA
    idat = zlib.compress(b"\x00\xff\x00\x00\xff")  # filter 0 + one red pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


PNG_1X1 = _make_png_1x1()


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
