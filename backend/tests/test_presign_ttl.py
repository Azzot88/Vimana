"""Presigned-URL lifetime is chosen by what the object is worth.

A presigned URL is a bearer token for one object: whoever holds the link can
fetch the file until it expires, with no session and no authorization check. It
leaks the ordinary ways links leak — history, referrer, a shared screenshot.

So an avatar and a passport scan should not get the same window. Found during
the IDOR audit (2026-07-29): everything was on the same one-hour TTL.
"""
from app.core.storage import (
    PRESIGN_TTL_DEFAULT,
    PRESIGN_TTL_SENSITIVE,
    presign_ttl_for_kind,
)
from app.models.deal import AttachmentKind


def test_identity_documents_get_the_short_window():
    assert presign_ttl_for_kind("identity_doc") == PRESIGN_TTL_SENSITIVE


def test_ordinary_attachments_keep_the_default():
    assert presign_ttl_for_kind("photo") == PRESIGN_TTL_DEFAULT
    assert presign_ttl_for_kind("document") == PRESIGN_TTL_DEFAULT


def test_unknown_kind_is_not_treated_as_sensitive():
    """Defaulting an unrecognised kind to the *short* window would silently
    break ordinary downloads; defaulting to long is the safe failure here
    because the sensitive kind is the one explicitly named."""
    assert presign_ttl_for_kind(None) == PRESIGN_TTL_DEFAULT
    assert presign_ttl_for_kind("something_new") == PRESIGN_TTL_DEFAULT


def test_sensitive_window_is_actually_shorter():
    assert PRESIGN_TTL_SENSITIVE < PRESIGN_TTL_DEFAULT


def test_s3_client_is_built_once_per_process(monkeypatch):
    """T_PERF.1 — one client, not one per call.

    Building it parses botocore's S3 service model, and `get_presigned_url`
    runs once per attachment: a vault page with a dozen photos used to build a
    dozen clients to sign a dozen URLs. The cache is cleared afterwards so a
    test that swaps R2 settings still gets a client built from them.
    """
    from app.core import storage

    monkeypatch.setattr(storage.settings, "R2_ENDPOINT", "https://r2.test")
    monkeypatch.setattr(storage.settings, "R2_ACCESS_KEY_ID", "k")
    monkeypatch.setattr(storage.settings, "R2_SECRET_ACCESS_KEY", "s")
    storage.reset_client_cache()
    try:
        assert storage.get_s3_client() is storage.get_s3_client()
    finally:
        storage.reset_client_cache()


def test_identity_doc_kind_still_exists():
    """The mapping keys off a string. If `AttachmentKind.identity_doc` is ever
    renamed, this test fails instead of the TTL quietly reverting to an hour."""
    assert AttachmentKind.identity_doc.value == "identity_doc"
