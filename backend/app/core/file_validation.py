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
rejected dirt never reaches storage.

4. **Malware scan** (T3.8 follow-up, done 2026-08-02) — the bytes go to clamd
   over `INSTREAM` before anything else touches them. The three layers above
   answer "is this really a JPEG"; this one answers "is this a *known bad*
   JPEG", which no amount of signature checking can.

   **Off unless configured, fail-closed once it is.** With `CLAMAV_HOST` unset
   the scan does not run and nothing in the product claims it did. With the
   host set, an unreachable or erroring scanner **rejects** the upload rather
   than waving it through: a vault whose files are shown to a counterparty must
   not quietly stop scanning because a container restarted. The switch is the
   presence of the setting, so the two states are impossible to confuse.
"""
from __future__ import annotations

import io
import logging
import os
import socket
import struct

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


#: clamd's own cap is 25 MB by default (`StreamMaxLength`); ours is smaller
#: still, so a chunk size well under it keeps the protocol simple.
_CLAMD_CHUNK = 64 * 1024


def _clamav_target() -> tuple[str, int] | None:
    """`(host, port)` when a scanner is configured, else None.

    Presence of `CLAMAV_HOST` is the on/off switch. There is deliberately no
    `CLAMAV_ENABLED` flag: two settings that can disagree would let the product
    be configured to claim scanning while pointing at nothing.
    """
    host = os.getenv("CLAMAV_HOST", "").strip()
    if not host:
        return None
    try:
        port = int(os.getenv("CLAMAV_PORT", "3310").strip() or 3310)
    except ValueError:
        port = 3310
    return host, port


def scan_for_malware(data: bytes) -> None:
    """Send the bytes to clamd and raise `FileValidationError` on anything but OK.

    Raw `INSTREAM` over a socket rather than a client library: the only
    maintained-looking option on PyPI (`clamd`) last shipped in 2018, and the
    protocol here is a length-prefixed stream terminated by a zero-length
    chunk. Taking an unmaintained dependency to avoid twenty lines is the wrong
    trade for a security control.

    A timeout, refused connection or malformed reply is a **rejection**, not a
    pass. The alternative — accepting uploads while the scanner is down —
    turns "we scan uploads" into a statement that is true only when convenient.
    """
    target = _clamav_target()
    if target is None:
        return

    host, port = target
    try:
        with socket.create_connection((host, port), timeout=10.0) as sock:
            sock.settimeout(10.0)
            sock.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), _CLAMD_CHUNK):
                chunk = data[offset : offset + _CLAMD_CHUNK]
                sock.sendall(struct.pack("!L", len(chunk)) + chunk)
            sock.sendall(struct.pack("!L", 0))

            reply = b""
            while b"\0" not in reply and len(reply) < 4096:
                part = sock.recv(4096)
                if not part:
                    break
                reply += part
    except OSError as exc:
        logger.error("clamav unreachable at %s:%s — rejecting upload: %s", host, port, exc)
        raise FileValidationError("virus scan unavailable")

    answer = reply.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
    if answer.endswith("OK"):
        return
    if "FOUND" in answer:
        # The signature name is logged, never returned: telling an uploader
        # which signature matched is a free oracle for tuning the next attempt.
        logger.warning("clamav rejected an upload: %s", answer)
        raise FileValidationError("file rejected by virus scan")
    logger.error("clamav answered unexpectedly: %.200s", answer)
    raise FileValidationError("virus scan unavailable")


def validate_upload(data: bytes, declared_mime: str) -> None:
    """Raise `FileValidationError` unless `data` really is `declared_mime`.

    Callers map the error to HTTP 422 and log `reason` — metadata only, the
    file bytes are never logged.
    """
    if len(data) < 12:
        raise FileValidationError("file too small to be valid")

    # Before the structural checks: a known-bad file should be refused whether
    # or not it is also a well-formed JPEG, and the cheapest way to guarantee
    # that ordering is to put the scan first.
    scan_for_malware(data)

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
