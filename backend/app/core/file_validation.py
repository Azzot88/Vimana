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

   **Fail-open with a queue** (owner's decision 2026-08-02). An unreachable or
   unconfigured scanner does not block the upload; it records `pending` on the
   attachment, alerts the administrators and leaves the file for
   `tasks.malware_rescan` to pick up. A found signature still refuses the
   upload outright — that is the one case where we know something.

   The trade being accepted, stated plainly: between upload and the deferred
   scan the file is downloadable by the counterparty **unscanned**. The
   alternative was breaking every upload whenever a container restarted, and
   the owner chose availability. `pending` is therefore never a synonym for
   safe, and no screen may render it as one.
"""
from __future__ import annotations

import io
import logging
import os
import socket
import struct
import time

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


#: The three things we can know about a file. `PENDING` covers both "no scanner
#: configured" and "scanner did not answer" on purpose: from the reader's side
#: they are the same situation — nobody has looked — and a separate word for
#: one of them would invite treating it as safer than the other.
SCAN_PENDING = "pending"
SCAN_CLEAN = "clean"
SCAN_INFECTED = "infected"


def scan_for_malware(data: bytes) -> str:
    """Send the bytes to clamd. Returns one of the three `SCAN_*` states.

    Raw `INSTREAM` over a socket rather than a client library: the only
    maintained-looking option on PyPI (`clamd`) last shipped in 2018, and the
    protocol here is a length-prefixed stream terminated by a zero-length
    chunk. Taking an unmaintained dependency to avoid twenty lines is the wrong
    trade for a security control.

    Never raises for infrastructure problems — a timeout, a refused connection
    or a malformed reply all return `SCAN_PENDING` and alert the
    administrators. Refusing the upload instead was the earlier design and the
    owner replaced it: an outage should cost a delayed check, not a broken
    product. Only `SCAN_INFECTED` is a fact about the file, and only the caller
    turns that into a refusal.
    """
    target = _clamav_target()
    if target is None:
        return SCAN_PENDING

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
        logger.error("clamav unreachable at %s:%s — queueing file: %s", host, port, exc)
        alert_scanner_down(f"{host}:{port} — {type(exc).__name__}")
        return SCAN_PENDING

    answer = reply.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
    if answer.endswith("OK"):
        return SCAN_CLEAN
    if "FOUND" in answer:
        # The signature name is logged, never returned: telling an uploader
        # which signature matched is a free oracle for tuning the next attempt.
        logger.warning("clamav found a signature: %s", answer)
        return SCAN_INFECTED
    logger.error("clamav answered unexpectedly: %.200s", answer)
    alert_scanner_down(f"{host}:{port} — unexpected reply")
    return SCAN_PENDING


#: Throttle for the administrator alert. Without it, a scanner that goes down
#: during an active upload session produces one message per file — which is how
#: an alert channel gets muted, and then the next real alert goes unread.
_ALERT_INTERVAL_SECONDS = 3600
_last_alert_at: float = 0.0


def alert_scanner_down(detail: str) -> None:
    """Tell the administrators the scanner is not answering, at most hourly.

    Fire-and-forget through Celery: an upload must not fail because the alert
    could not be delivered — that would reintroduce the failure mode this whole
    redesign removed.
    """
    global _last_alert_at
    now = time.monotonic()
    if now - _last_alert_at < _ALERT_INTERVAL_SECONDS:
        return
    _last_alert_at = now
    try:
        from app.tasks.notifications import notify_admins_scanner_down

        notify_admins_scanner_down.delay(detail)
    except Exception:
        logger.warning("could not dispatch the scanner-down alert", exc_info=True)


def validate_upload(data: bytes, declared_mime: str) -> str:
    """Raise `FileValidationError` unless `data` really is `declared_mime`.

    Returns the scan state (`SCAN_CLEAN` or `SCAN_PENDING`) so the caller can
    record it on the row it is about to write. Callers that have nowhere to put
    it — the avatar path has no attachment — may ignore the value; what they
    must not do is treat "no exception" as "scanned".

    Callers map the error to HTTP 422 and log `reason` — metadata only, the
    file bytes are never logged.
    """
    if len(data) < 12:
        raise FileValidationError("file too small to be valid")

    # Before the structural checks: a known-bad file should be refused whether
    # or not it is also a well-formed JPEG, and the cheapest way to guarantee
    # that ordering is to put the scan first.
    status = scan_for_malware(data)
    if status == SCAN_INFECTED:
        raise FileValidationError("file rejected by virus scan")

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

    return status
