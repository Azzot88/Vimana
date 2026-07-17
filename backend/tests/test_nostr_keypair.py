"""T2.2 — user Nostr keypair (custodial + self-custody + signing)."""
import pytest
from sqlalchemy import text as sa_text


async def test_registration_generates_custodial_keypair(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("kp")
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": SEED_PASSWORD,
            "display_name": "KP user",
        },
    )
    assert resp.status_code == 201, resp.text

    # Login and fetch /me
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    status = await client.get("/api/me/keypair/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["npub"] is not None
    assert len(body["npub"]) == 64  # 32 bytes hex
    assert body["key_self_custody"] is False
    assert body["has_encrypted_nsec"] is True


async def test_nsec_never_plaintext_in_db(client, session_maker):
    from tests.conftest import SEED_PASSWORD, unique_email
    from app.models.user import User
    from sqlalchemy import select

    email = unique_email("kp-privacy")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "P"},
    )

    async with session_maker() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        assert user.nsec_encrypted is not None
        assert user.nsec_nonce is not None
        assert len(user.nsec_nonce) == 12
        # Ciphertext should not contain the ASCII representation of a hex string;
        # a 64-char hex nsec would leak if stored plaintext.
        raw = bytes(user.nsec_encrypted)
        # crude smoke: no 32+ consecutive lowercase hex chars
        import re
        assert not re.search(rb"[0-9a-f]{32,}", raw)


async def test_export_requires_correct_password(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("kp-exp")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "E"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    bad = await client.post(
        "/api/me/keypair/export", headers=headers, json={"password": "wrong-pw"}
    )
    assert bad.status_code == 401

    ok = await client.post(
        "/api/me/keypair/export", headers=headers, json={"password": SEED_PASSWORD}
    )
    assert ok.status_code == 200
    assert len(ok.json()["nsec_hex"]) == 64
    assert len(ok.json()["npub_hex"]) == 64


async def test_claim_deletes_encrypted_nsec(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("kp-claim")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "C"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    claim = await client.post("/api/me/keypair/claim", headers=headers)
    assert claim.status_code == 200
    body = claim.json()
    assert body["key_self_custody"] is True
    assert body["has_encrypted_nsec"] is False

    # Export after claim → 404
    exp = await client.post(
        "/api/me/keypair/export", headers=headers, json={"password": SEED_PASSWORD}
    )
    assert exp.status_code == 404


async def test_import_replaces_keypair_and_marks_self_custody(client):
    from tests.conftest import SEED_PASSWORD, unique_email
    from app.core.keypair import generate_keypair

    email = unique_email("kp-imp")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "I"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    foreign_nsec, foreign_npub = generate_keypair()
    imp = await client.post(
        "/api/me/keypair/import",
        headers=headers,
        json={"nsec_hex": foreign_nsec},
    )
    assert imp.status_code == 200
    assert imp.json()["npub"] == foreign_npub
    assert imp.json()["key_self_custody"] is True
    assert imp.json()["has_encrypted_nsec"] is False


async def test_import_npub_only_tracking(client):
    from tests.conftest import SEED_PASSWORD, unique_email
    from app.core.keypair import generate_keypair

    email = unique_email("kp-track")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "T"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    _, npub_only = generate_keypair()
    imp = await client.post(
        "/api/me/keypair/import",
        headers=headers,
        json={"npub_hex": npub_only},
    )
    assert imp.status_code == 200
    assert imp.json()["npub"] == npub_only
    assert imp.json()["key_self_custody"] is True


async def test_import_requires_at_least_one_field(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("kp-empty")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "E"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post("/api/me/keypair/import", headers=headers, json={})
    assert resp.status_code == 422


async def test_bad_hex_rejected(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("kp-hex")
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "H"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/me/keypair/import", headers=headers, json={"nsec_hex": "not-hex-really"}
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────
# Server-side signing of DealVault messages / DealEvents
# ─────────────────────────────────────────────────────────────


async def test_message_from_new_user_gets_server_signed(client):
    """New (custodial) user → server signs vault messages automatically."""
    from datetime import datetime, timedelta, timezone
    from tests.conftest import SEED_PASSWORD, unique_email

    # Fresh carrier
    carrier_email = unique_email("sig-c")
    await client.post(
        "/api/auth/register",
        json={
            "email": carrier_email,
            "password": SEED_PASSWORD,
            "display_name": "SigC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": carrier_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    # Fresh sender
    sender_email = unique_email("sig-s")
    await client.post(
        "/api/auth/register",
        json={"email": sender_email, "password": SEED_PASSWORD, "display_name": "SigS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": sender_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}

    trip_r = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "SIG",
            "destination": "TST",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip_r.json()["id"]

    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000009999",
                "origin": "SIG",
                "destination": "TST",
                "category": "document",
                "declared_value": 50.0,
            },
        },
    )
    deal_id = match.json()["id"]

    resp = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=s_headers,
        json={"text": "Hello with a signed envelope"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["nostr_sig"] is not None
    assert len(body["nostr_sig"]) == 128  # 64 bytes hex


async def test_self_custody_vault_message_requires_pre_signed(client):
    """After claim → server can't sign vault messages; POST without nostr_sig → 422.

    Deal-state events remain OK for self-custody (lenient, unsigned) — only the
    user-content vault message path is strict.
    """
    from datetime import datetime, timedelta, timezone
    from tests.conftest import SEED_PASSWORD, unique_email

    c_email = unique_email("scc")
    await client.post(
        "/api/auth/register",
        json={
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "SCC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "SCC",
            "destination": "SLF",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]

    s_email = unique_email("selfs")
    await client.post(
        "/api/auth/register",
        json={"email": s_email, "password": SEED_PASSWORD, "display_name": "SelfS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}
    await client.post("/api/me/keypair/claim", headers=s_headers)

    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000008888",
                "origin": "SCC",
                "destination": "SLF",
                "category": "document",
                "declared_value": 30.0,
            },
        },
    )
    # Deal state events are lenient — self-custody proceeds without sig.
    assert match.status_code == 201, match.json()
    deal_id = match.json()["id"]

    # But vault message under self-custody without pre-signed sig → 422.
    msg = await client.post(
        f"/api/deals/{deal_id}/dealvault/messages",
        headers=s_headers,
        json={"text": "unsigned attempt"},
    )
    assert msg.status_code == 422
    assert "self-custody" in msg.json()["detail"].lower()
