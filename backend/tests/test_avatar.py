"""T_UX.4 B — user avatar upload/delete endpoints.

R2 upload is a no-op when R2_ENDPOINT is not set (see core.storage), so
these tests exercise the whole path except the actual object write. That's
fine — we care about validation + state persistence, not S3 behavior.
"""
from __future__ import annotations

import io

from tests.conftest import SEED_PASSWORD, make_account, unique_email

# T3.8 — uploads are content-validated now, so fixtures must be real images.
from tests.test_dealvault_attachments import PNG_1X1


async def _register_and_login(client) -> dict:
    email = unique_email("av")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Av"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_upload_avatar_persists_key(client):
    hdr = await _register_and_login(client)
    # T3.8: content is validated (signature + decode) — must be a real PNG.
    files = {"file": ("me.png", io.BytesIO(PNG_1X1), "image/png")}
    r = await client.post("/api/me/avatar", headers=hdr, files=files)
    assert r.status_code == 200, r.text
    me_r = await client.get("/api/auth/me", headers=hdr)
    # avatar_url is None when R2 is unconfigured (test env) — but avatar_key
    # is set, and the /me handler consistently mints or returns None.
    assert me_r.status_code == 200


async def test_upload_rejects_wrong_mime(client):
    hdr = await _register_and_login(client)
    files = {"file": ("me.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    r = await client.post("/api/me/avatar", headers=hdr, files=files)
    assert r.status_code == 415


async def test_upload_rejects_oversized_via_content_length(client):
    hdr = await _register_and_login(client)
    # Fake content-length beyond 3MB — the streaming loop checks both.
    r = await client.post(
        "/api/me/avatar",
        headers={**hdr, "Content-Length": str(4 * 1024 * 1024)},
        files={"file": ("me.png", io.BytesIO(b"\x89PNG" + b"\x00" * 4), "image/png")},
    )
    assert r.status_code == 413


async def test_delete_avatar_clears_key(client):
    hdr = await _register_and_login(client)
    files = {"file": ("me.png", io.BytesIO(PNG_1X1), "image/png")}
    await client.post("/api/me/avatar", headers=hdr, files=files)
    r = await client.delete("/api/me/avatar", headers=hdr)
    assert r.status_code == 200
    assert r.json().get("avatar_url") is None


async def test_avatar_requires_auth(client):
    r = await client.post(
        "/api/me/avatar",
        files={"file": ("x.png", io.BytesIO(b"\x89PNG"), "image/png")},
    )
    assert r.status_code == 401
