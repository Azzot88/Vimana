"""T_UX.3 pt.4a — POST /api/auth/logout revokes JWT via Redis blacklist.

After logout, the same token must be rejected with 401. Idempotent for
already-expired or malformed tokens (204). Tests run against a real Redis
via docker-compose (test conftest doesn't stub it — Celery uses the same
instance).
"""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import SEED_PASSWORD, unique_email


async def _register_and_get_token(client) -> str:
    email = unique_email("logout")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "L"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return login.json()["access_token"]


async def test_logout_blacklists_token(client):
    token = await _register_and_get_token(client)
    hdr = {"Authorization": f"Bearer {token}"}

    # /me works before logout.
    r_before = await client.get("/api/auth/me", headers=hdr)
    assert r_before.status_code == 200

    # Logout succeeds.
    r_logout = await client.post("/api/auth/logout", headers=hdr)
    assert r_logout.status_code == 204

    # Same token now rejected — get_current_user checks Redis and 401s.
    r_after = await client.get("/api/auth/me", headers=hdr)
    assert r_after.status_code == 401, r_after.text
    assert "revoked" in r_after.json()["detail"].lower()


async def test_logout_is_idempotent_for_invalid_token(client):
    """A garbage token still gets a clean 204 — logout must always succeed
    client-side (no reason to error on a token we can't parse)."""
    r = await client.post(
        "/api/auth/logout", headers={"Authorization": "Bearer definitely-not-a-jwt"}
    )
    assert r.status_code == 204


async def test_second_logout_of_same_token_still_204(client):
    """Blacklisting twice must be a no-op — real users may double-click logout."""
    token = await _register_and_get_token(client)
    hdr = {"Authorization": f"Bearer {token}"}
    r1 = await client.post("/api/auth/logout", headers=hdr)
    r2 = await client.post("/api/auth/logout", headers=hdr)
    assert r1.status_code == 204
    assert r2.status_code == 204


async def test_other_users_token_unaffected_by_logout(client):
    """Logout of A must not touch B's token — jti scoping check."""
    token_a = await _register_and_get_token(client)
    token_b = await _register_and_get_token(client)
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    await client.post("/api/auth/logout", headers=hdr_a)

    # A revoked.
    r_a = await client.get("/api/auth/me", headers=hdr_a)
    assert r_a.status_code == 401
    # B still works.
    r_b = await client.get("/api/auth/me", headers=hdr_b)
    assert r_b.status_code == 200


async def test_new_login_after_logout_gets_working_token(client):
    """User can log back in and the new token works — old jti is revoked but
    the new token gets a fresh jti."""
    email = unique_email("relogin")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "R"},
    )
    login1 = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    old_token = login1.json()["access_token"]
    await client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {old_token}"}
    )

    login2 = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    new_token = login2.json()["access_token"]
    assert new_token != old_token
    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert r.status_code == 200
