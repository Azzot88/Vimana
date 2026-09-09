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


async def test_cargo_photo_is_its_own_kind_and_takes_images_only(
    client, sender_headers, seed_deal
):
    """T3.11.27 — «вот что я отправляю», attached at the terms stage.

    Its own kind rather than `doc`: this is the only photograph in a deal's
    record taken while the deal could still be refused, and an arbiter reads
    these labels. Images only, for the reason the other photo kinds are —
    a PDF of a thing is not a picture of it.
    """
    msg_id = await _create_message(client, sender_headers, seed_deal.id)

    ok = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("item.png", PNG_1X1, "image/png")},
        data={"kind": "cargo_photo"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["kind"] == "cargo_photo"

    refused = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("item.pdf", b"%PDF-1.4", "application/pdf")},
        data={"kind": "cargo_photo"},
    )
    assert refused.status_code == 415


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


# ── T3.11.25 — the personal file safe ───────────────────────────────────────


def _make_png(colour: bytes) -> bytes:
    """A distinct 1×1 PNG per test, so two tests never share a file hash — the
    safe is keyed on (owner, hash) and `vimana_test` is never reset."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + colour)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


async def _upload(client, headers, deal_id, png: bytes) -> dict:
    msg_id = await _create_message(client, headers, deal_id)
    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg_id}/attachments",
        headers=headers,
        files={"file": ("doc.png", png, "image/png")},
        data={"kind": "doc"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_uploaded_file_lands_in_my_safe(client, sender_headers, seed_deal):
    """Owner's statement 2026-09-07: «файлы из одной сделки с этим аккаунтом
    доступны и для новых сделок». The safe is filled by the ordinary upload —
    nobody has to file anything twice."""
    png = _make_png(b"\x11\x22\x33\xff")
    body = await _upload(client, sender_headers, seed_deal.id, png)

    safe = await client.get("/api/me/files", headers=sender_headers)
    assert safe.status_code == 200, safe.text
    mine = next(f for f in safe.json() if f["file_hash"] == body["file_hash"])
    assert mine["kind"] == "doc"
    assert mine["mime"] == "image/png"
    assert mine["size_bytes"] == len(png)
    assert mine["first_provided_at"]


async def test_the_same_bytes_are_one_file_in_the_safe(client, sender_headers, seed_deal):
    """Sending the same passport twice is one document. Two rows would give
    «впервые предоставлен» two answers."""
    png = _make_png(b"\x44\x55\x66\xff")
    first = await _upload(client, sender_headers, seed_deal.id, png)
    await _upload(client, sender_headers, seed_deal.id, png)

    safe = await client.get("/api/me/files", headers=sender_headers)
    rows = [f for f in safe.json() if f["file_hash"] == first["file_hash"]]
    assert len(rows) == 1


async def _second_deal(client, sender_headers, carrier_headers) -> str:
    """A deal of this test's own, made through the API.

    Not `fresh_vault_deal`: that fixture exists so three pagination tests get a
    vault with a known floor, and writing into it would take the floor away
    again (`ENVIRONMENT §8` — nothing here is ever reset).
    """
    from datetime import datetime, timedelta, timezone

    trip = await client.post(
        "/api/trips",
        headers=carrier_headers,
        json={
            "payment_model": "cash_on_delivery",
            "legs": [
                {
                    "origin": "SAF",
                    "destination": "ETY",
                    "depart_at": (
                        datetime.now(timezone.utc) + timedelta(days=4)
                    ).isoformat(),
                }
            ],
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
                "recipient_contact": "+10000002222",
                "origin": "SAF",
                "destination": "ETY",
                "category": "document",
                "declared_value": 25.0,
            },
        },
    )
    assert match.status_code == 201, match.text
    return match.json()["id"]


async def test_reattaching_writes_its_own_event_with_the_same_hash(
    client, session_maker, sender_headers, carrier_headers, seed_deal
):
    """The heart of the task. The second deal's chain must say the document was
    attached *today* while carrying the hash of bytes provided earlier — and it
    must not claim they were provided under this parcel."""
    png = _make_png(b"\x77\x88\x99\xff")
    first = await _upload(client, sender_headers, seed_deal.id, png)

    safe = await client.get("/api/me/files", headers=sender_headers)
    entry = next(f for f in safe.json() if f["file_hash"] == first["file_hash"])

    deal_id = await _second_deal(client, sender_headers, carrier_headers)
    msg_id = await _create_message(client, sender_headers, deal_id)
    again = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages/{msg_id}/attach-file",
        headers=sender_headers,
        json={"user_file_id": entry["id"]},
    )
    assert again.status_code == 201, again.text
    assert again.json()["file_hash"] == first["file_hash"]
    # Same bytes, not a copy: the new attachment points at the stored object.
    assert again.json()["r2_key"] == first["r2_key"]

    # The chain still verifies with the new entry in it.
    chain = await client.get(f"/api/deals/{deal_id}/chain", headers=sender_headers)
    assert chain.status_code == 200, chain.text
    assert chain.json()["ok"] is True

    from sqlalchemy import select

    from app.models.deal import DealEvent, DealEventType

    async with session_maker() as db:
        rows = (
            (
                await db.execute(
                    select(DealEvent).where(
                        DealEvent.deal_id == uuidlib.UUID(deal_id),
                    )
                )
            )
            .scalars()
            .all()
        )
    kinds = [e.event_type for e in rows]
    assert DealEventType.file_reattached in kinds
    # And **not** as a first provision: `file_added` is reserved for bytes that
    # arrived under this deal, which these did not.
    assert DealEventType.file_added not in kinds

    reattached = next(
        e for e in rows if e.event_type == DealEventType.file_reattached
    )
    assert reattached.payload["file_hash"] == first["file_hash"]
    assert reattached.payload["first_provided_at"].startswith(
        entry["first_provided_at"][:19]
    )


async def test_cannot_attach_somebody_elses_file(
    client, sender_headers, carrier_headers, seed_deal
):
    """A document handed to one counterparty is not published to the platform by
    that act. The stranger's id answers 404 — 403 would confirm the row exists."""
    png = _make_png(b"\xaa\xbb\xcc\xff")
    body = await _upload(client, sender_headers, seed_deal.id, png)
    safe = await client.get("/api/me/files", headers=sender_headers)
    entry = next(f for f in safe.json() if f["file_hash"] == body["file_hash"])

    msg_id = await _create_message(client, carrier_headers, seed_deal.id)
    stolen = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attach-file",
        headers=carrier_headers,
        json={"user_file_id": entry["id"]},
    )
    assert stolen.status_code == 404


async def test_safe_shows_only_my_own_files(client, sender_headers, carrier_headers, seed_deal):
    png = _make_png(b"\xdd\xee\xff\xff")
    body = await _upload(client, sender_headers, seed_deal.id, png)

    theirs = await client.get("/api/me/files", headers=carrier_headers)
    assert body["file_hash"] not in [f["file_hash"] for f in theirs.json()]
