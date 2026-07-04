import uuid

from tests.conftest import SEED_PASSWORD, unique_email


async def test_register_new_user(client):
    email = unique_email("reg")
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "test-password-1",
            "display_name": "Reg User",
            "is_carrier": False,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert body["display_name"] == "Reg User"
    assert body["is_carrier"] is False


async def test_register_duplicate_email(client, seed_carrier):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": seed_carrier.email,
            "password": "test-password-1",
            "display_name": "Duplicate",
        },
    )
    assert resp.status_code == 409


async def test_register_requires_email_or_phone(client):
    resp = await client.post(
        "/api/auth/register",
        json={"password": "test-password-1", "display_name": "No contact"},
    )
    assert resp.status_code == 422


async def test_login_success(client, seed_sender):
    resp = await client.post(
        "/api/auth/login",
        json={"login": seed_sender.email, "password": SEED_PASSWORD},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password(client, seed_sender):
    resp = await client.post(
        "/api/auth/login",
        json={"login": seed_sender.email, "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(client):
    resp = await client.post(
        "/api/auth/login",
        json={"login": "ghost@vimana.test", "password": "any"},
    )
    assert resp.status_code == 401


async def test_me_returns_current_user(client, sender_headers, seed_sender):
    resp = await client.get("/api/auth/me", headers=sender_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == seed_sender.email


async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_patch_me_updates_display_name(client, sender_headers):
    new_name = "Updated Sender Name"
    resp = await client.patch(
        "/api/auth/me", headers=sender_headers, json={"display_name": new_name}
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == new_name


async def test_patch_me_updates_phone(client, sender_headers):
    new_phone = f"+1555{uuid.uuid4().hex[:7]}"
    resp = await client.patch(
        "/api/auth/me", headers=sender_headers, json={"phone": new_phone}
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == new_phone


async def test_register_without_phone_succeeds(client):
    email = unique_email("nophone")
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "test-password-1",
            "display_name": "No Phone User",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["phone"] is None


async def test_register_normalizes_email_lowercase(client):
    raw_email = f"MixedCase-{uuid.uuid4().hex[:6]}@Vimana.Test"
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": raw_email,
            "password": "test-password-1",
            "display_name": "Case User",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == raw_email.lower()


async def test_login_is_case_insensitive_for_email(client):
    raw_email = f"Case-Login-{uuid.uuid4().hex[:6]}@Vimana.Test"
    password = "test-password-1"
    reg = await client.post(
        "/api/auth/register",
        json={"email": raw_email, "password": password, "display_name": "CI Login"},
    )
    assert reg.status_code == 201

    for variant in (raw_email, raw_email.lower(), raw_email.upper()):
        resp = await client.post(
            "/api/auth/login", json={"login": variant, "password": password}
        )
        assert resp.status_code == 200, f"failed for variant {variant!r}"
        assert "access_token" in resp.json()


async def test_login_trims_whitespace(client):
    email = unique_email("trim")
    password = "test-password-1"
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Trim"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"login": f"  {email.upper()}  ", "password": password},
    )
    assert resp.status_code == 200
