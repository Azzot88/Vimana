import uuid

from tests.conftest import SEED_PASSWORD, make_account, unique_email


async def test_register_new_user(client):
    email = unique_email("reg")
    resp = await make_account({
            "email": email,
            "password": "test-password-1",
            "display_name": "Reg User",
            "can_carry": False,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert body["display_name"] == "Reg User"
    assert body["can_carry"] is False
    assert body["can_send"] is True
    assert body["active_mode"] == "sender"


async def test_register_duplicate_email(client, seed_carrier):
    resp = await make_account({
            "email": seed_carrier.email,
            "password": "test-password-1",
            "display_name": "Duplicate",
        },
    )
    assert resp.status_code == 409


async def test_register_requires_email(client):
    """T3.11 — email is the only identifier; phone left the auth path."""
    resp = await make_account({"password": "test-password-1", "display_name": "No contact"},
    )
    assert resp.status_code == 422


async def test_register_rejects_phone_only(client):
    resp = await make_account({
            "phone": "+15550001111",
            "password": "test-password-1",
            "display_name": "Phone Only",
        },
    )
    assert resp.status_code == 422


async def test_login_by_phone_no_longer_works(client, seed_sender):
    """A phone-shaped login matches no email and falls through to 401 —
    the same answer a wrong password gets, so it leaks nothing."""
    resp = await client.post(
        "/api/auth/login",
        json={"login": "+15550001111", "password": SEED_PASSWORD},
    )
    assert resp.status_code == 401


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
    """T3.25 — the number must now be a real one.

    The old value was `+1555` plus random hex, which parsed as nothing. That it
    used to pass is the point: the column took any text, so two spellings of
    one number were two numbers and `UNIQUE` could not tell.
    """
    # A real UAE mobile prefix with a non-zero subscriber part: libphonenumber
    # validates against actual numbering plans, and `+1202` plus seven random
    # digits is invalid whenever the first of them is 0 or 1.
    new_phone = f"+97150{1_000_000 + uuid.uuid4().int % 9_000_000}"
    resp = await client.patch(
        "/api/auth/me", headers=sender_headers, json={"phone": new_phone}
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == new_phone


async def test_register_without_phone_succeeds(client):
    email = unique_email("nophone")
    resp = await make_account({
            "email": email,
            "password": "test-password-1",
            "display_name": "No Phone User",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["phone"] is None


async def test_register_normalizes_email_lowercase(client):
    raw_email = f"MixedCase-{uuid.uuid4().hex[:6]}@Vimana.Test"
    resp = await make_account({
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
    reg = await make_account({"email": raw_email, "password": password, "display_name": "CI Login"},
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
    await make_account({"email": email, "password": password, "display_name": "Trim"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"login": f"  {email.upper()}  ", "password": password},
    )
    assert resp.status_code == 200
