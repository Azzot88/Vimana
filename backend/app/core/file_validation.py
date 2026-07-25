"""T3.8 — content validation for uploaded files (anti-dirt).

The MIME whitelist (T1.19) trusts the client's Content-Type header, which is
trivially forged: an executable renamed to `.jpg` sails through. This module
validates the *bytes*:

1. **Signature whitelist** — the content must carry the magic bytes of the
   *declared* type. This is stricter than a blacklist: MZ/ELF/shebang/HTML and
   every other non-matching payload fail automatically because they don't look
   like the declared type, not because we enumerated them.
2. **Full image decode** (jpeg/png/webp) — Pillow `verify()` + a real `load()`.
   A file with a valid header but a broken or foreign body (polyglots,
   truncated data) dies here. HEIC/HEIF get signature-only validation: Pillow
   has no native HEIC codec and pulling in pillow-heif is not worth it for a
   check the signature already covers.
3. **PDF** — `%PDF-` header. Content sanitising (embedded JS etc.) is out of
   scope; PDFs are only served back for download, never rendered server-side.

Validation runs on the fully-buffered upload *before* the R2 write, so
rejected dirt never reaches storage. ClamAV is a deliberate follow-up, not
part of this layer.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

#: ISO BMFF brands accepted as HEIC/HEIF (bytes 8..12 of the `ftyp` box).
_HEIF_BRANDS = {
    b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs",
    b"mif1", b"msf1", b"heif",
}

#: Types Pillow decodes natively — these get the full decode check.
_PILLOW_DECODABLE = {"image/jpeg", "image/png", "image/webp"}


class FileValidationError(ValueError):
    """Content does not match the declared type. `reason` is log-safe (никогда
    не содержит байтов файла)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _signature_matches(data: bytes, declared_mime: str) -> bool:
    if declared_mime == "image/jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if declared_mime == "image/png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if declared_mime == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if declared_mime in ("image/heic", "image/heif"):
        return data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS
    if declared_mime == "application/pdf":
        return data[:5] == b"%PDF-"
    return False


#: Signature sniffing order for `validate_document` (declared MIME unknown or
#: untrusted): identity documents are photos or PDFs.
_DOCUMENT_MIMES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
)


def sniff_mime(data: bytes) -> str | None:
    """Detect the content type by signature alone. None = nothing we accept."""
    for mime in _DOCUMENT_MIMES:
        if _signature_matches(data, mime):
            return mime
    return None


def validate_document(data: bytes) -> str:
    """T3.8 — validate an identity-document upload where the client's declared
    MIME is not trusted at all: sniff the real type, then run the same decode
    check as `validate_upload`. Returns the detected MIME.
    """
    if len(data) < 12:
        raise FileValidationError("file too small to be valid")
    detected = sniff_mime(data)
    if detected is None:
        raise FileValidationError("content is not an accepted document type")
    validate_upload(data, detected)
    return detected


def validate_upload(data: bytes, declared_mime: str) -> None:
    """Raise `FileValidationError` unless `data` really is `declared_mime`.

    Callers map the error to HTTP 422 and log `reason` — metadata only, the
    file bytes are never logged.
    """
    if len(data) < 12:
        raise FileValidationError("file too small to be valid")

    if not _signature_matches(data, declared_mime):
        raise FileValidationError(
            f"content signature does not match declared type {declared_mime}"
        )

    if declared_mime in _PILLOW_DECODABLE:
        from PIL import Image

        try:
            # verify() checks structure without decoding pixels; a second open
            # + load() forces the full decode (verify() leaves the parser in an
            # unusable state, hence two opens — documented Pillow behaviour).
            Image.open(io.BytesIO(data)).verify()
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            raise FileValidationError(f"image does not decode: {type(exc).__name__}")

        fmt = (img.format or "").lower()
        expected = declared_mime.removeprefix("image/")
        if fmt != expected:
            raise FileValidationError(
                f"decoded format '{fmt}' does not match declared {declared_mime}"
            )
