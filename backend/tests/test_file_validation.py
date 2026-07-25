"""T3.8 — content validation for uploads (anti-dirt).

Unit tests hit `validate_upload` directly (fast, exhaustive on signatures);
API tests prove the wiring: dirty bytes die with 422 before the R2 write, on
both the DealVault attachment path and the avatar path.
"""
import io

import pytest
from PIL import Image

from app.core.file_validation import (
    FileValidationError,
    sniff_mime,
    validate_document,
    validate_upload,
)
from tests.test_dealvault_attachments import PNG_1X1


def _image_bytes(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


JPEG_REAL = _image_bytes("JPEG")
WEBP_REAL = _image_bytes("WEBP")
PDF_MIN = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
HEIC_MIN = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"

MZ_EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"
ELF_BIN = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 16
SHEBANG = b"#!/bin/sh\nrm -rf /\n"
HTML_DOC = b"<html><script>alert(1)</script></html>"


# ─────────────────────────────────────────────────────────────
# 1. Unit: signature whitelist
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("dirty", [MZ_EXE, ELF_BIN, SHEBANG, HTML_DOC])
@pytest.mark.parametrize(
    "declared", ["image/jpeg", "image/png", "image/webp", "application/pdf"]
)
def test_dirty_payloads_rejected_for_every_declared_type(dirty, declared):
    with pytest.raises(FileValidationError):
        validate_upload(dirty, declared)


def test_too_small_rejected():
    with pytest.raises(FileValidationError, match="too small"):
        validate_upload(b"MZ", "image/jpeg")


def test_signature_of_other_type_rejected():
    # Real PNG declared as JPEG — signature check catches the lie.
    with pytest.raises(FileValidationError, match="signature"):
        validate_upload(PNG_1X1, "image/jpeg")


@pytest.mark.parametrize(
    "data,declared",
    [
        (PNG_1X1, "image/png"),
        (JPEG_REAL, "image/jpeg"),
        (WEBP_REAL, "image/webp"),
        (PDF_MIN, "application/pdf"),
        (HEIC_MIN, "image/heic"),
        (HEIC_MIN, "image/heif"),
    ],
)
def test_valid_content_passes(data, declared):
    validate_upload(data, declared)  # must not raise


def test_heic_wrong_brand_rejected():
    avif = b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00mif1avif"
    with pytest.raises(FileValidationError):
        validate_upload(avif, "image/heic")


# ─────────────────────────────────────────────────────────────
# 2. Unit: decode layer (valid header, broken body)
# ─────────────────────────────────────────────────────────────


def test_png_header_with_garbage_body_rejected():
    polyglot = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    with pytest.raises(FileValidationError, match="does not decode"):
        validate_upload(polyglot, "image/png")


def test_truncated_png_rejected():
    with pytest.raises(FileValidationError):
        validate_upload(PNG_1X1[: len(PNG_1X1) // 2], "image/png")


# ─────────────────────────────────────────────────────────────
# 2b. Unit: document sniffing (declared MIME not trusted)
# ─────────────────────────────────────────────────────────────


def test_sniff_detects_each_document_type():
    assert sniff_mime(PNG_1X1) == "image/png"
    assert sniff_mime(JPEG_REAL) == "image/jpeg"
    assert sniff_mime(WEBP_REAL) == "image/webp"
    assert sniff_mime(PDF_MIN) == "application/pdf"
    assert sniff_mime(HEIC_MIN) == "image/heic"
    assert sniff_mime(MZ_EXE) is None


def test_validate_document_returns_detected_mime():
    assert validate_document(PNG_1X1) == "image/png"
    assert validate_document(PDF_MIN) == "application/pdf"


@pytest.mark.parametrize("dirty", [MZ_EXE, ELF_BIN, SHEBANG, HTML_DOC])
def test_validate_document_rejects_dirt(dirty):
    with pytest.raises(FileValidationError):
        validate_document(dirty)


# ─────────────────────────────────────────────────────────────
# 3. API wiring: DealVault attachments + avatar
# ─────────────────────────────────────────────────────────────


async def _message_id(client, headers, deal_id) -> str:
    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=headers,
        json={"text": "file incoming", "is_system": False},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_exe_renamed_to_jpg_rejected_422(client, sender_headers, seed_deal):
    msg_id = await _message_id(client, sender_headers, seed_deal.id)
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("photo.jpg", MZ_EXE, "image/jpeg")},
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 422
    assert "validation" in resp.json()["detail"]


async def test_corrupt_png_rejected_422(client, sender_headers, seed_deal):
    msg_id = await _message_id(client, sender_headers, seed_deal.id)
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={
            "file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png"),
        },
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 422


async def test_valid_jpeg_still_uploads(client, sender_headers, seed_deal):
    msg_id = await _message_id(client, sender_headers, seed_deal.id)
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("photo.jpg", JPEG_REAL, "image/jpeg")},
        data={"kind": "handoff_photo"},
    )
    assert resp.status_code == 201, resp.text


async def test_valid_pdf_doc_still_uploads(client, sender_headers, seed_deal):
    msg_id = await _message_id(client, sender_headers, seed_deal.id)
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("contract.pdf", PDF_MIN, "application/pdf")},
        data={"kind": "doc"},
    )
    assert resp.status_code == 201, resp.text


async def test_avatar_exe_as_jpeg_rejected_422(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("fv")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "FV"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.post(
        "/api/me/avatar",
        headers=hdr,
        files={"file": ("me.jpg", io.BytesIO(MZ_EXE), "image/jpeg")},
    )
    assert resp.status_code == 422


async def test_verification_self_upload_rejects_dirt(client, sender_headers):
    resp = await client.post(
        "/api/me/verification/self-upload",
        headers=sender_headers,
        data={"doc_type": "passport", "doc_country": "AE"},
        files={"file": ("id.jpg", SHEBANG * 10, "image/jpeg")},
    )
    assert resp.status_code == 422
    assert "validation" in resp.json()["detail"]
