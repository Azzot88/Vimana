"""T3.14 — passkey endpoints, everything that does not need a real authenticator.

Signature verification, CBOR parsing and attestation belong to `py_webauthn`;
re-testing a library proves nothing. What is tested here is our half: ceremony
state, ownership, and the guard that stops someone locking themselves out.

Producing a *valid* WebAuthn response needs an authenticator (or a software one
generating attestation objects), so the happy path is covered by the Playwright
spec with a virtual authenticator rather than here. That is stated plainly
rather than faked with a mock that would assert nothing.
"""
import uuid

from sqlalchemy import select

from app.models.user import User
from app.models.webauthn import WebAuthnCredential
from tests.conftest import SEED_PASSWORD, unique_email


async def _register(client, *, password=True, prefix="pk") -> dict[str, str]:
    email = unique_email(prefix)
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": "Passkey"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _add_credential(session_maker, email_or_id, *, name="Device") -> uuid.UUID:
    async with session_maker() as db:
        cred = WebAuthnCredential(
            user_id=email_or_id,
            credential_id=uuid.uuid4().bytes,
            public_key=b"pk",
            device_name=name,
        )
        db.add(cred)
        await db.commit()
        await db.refresh(cred)
        return cred.id


async def _step_up(client, headers) -> str:
    """T3.15 — unlinking a device needs a fresh confirmation. Proof handling
    itself is `test_step_up.py`; here it is just a precondition."""
    from tests.conftest import step_up_token

    return await step_up_token(client, headers, "unlink_passkey")


def _with_step_up(headers: dict[str, str], token: str) -> dict[str, str]:
    """Header, not query string — a URL lands in access logs, history and
    `Referer`, and a confirmation grant has no business in any of them."""
    return {**headers, "X-Step-Up-Token": token}


async def _user_id(client, headers) -> uuid.UUID:
    me = await client.get("/api/auth/me", headers=headers)
    return uuid.UUID(me.json()["id"])


# ── options ──────────────────────────────────────────────────────────────────


async def test_register_options_requires_auth(client):
    resp = await client.post("/api/auth/passkey/register/options")
    assert resp.status_code == 401


async def test_register_options_returns_a_ceremony(client):
    headers = await _register(client)
    resp = await client.post("/api/auth/passkey/register/options", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ceremony_id"]
    assert body["options"]["challenge"]
    # Required for usernameless login — without it the browser cannot offer the
    # credential unprompted.
    assert body["options"]["authenticatorSelection"]["residentKey"] == "required"


async def test_login_options_is_anonymous_and_names_no_credentials(client):
    """Empty `allowCredentials` on purpose: listing them would answer "does this
    account exist" to anyone who asks."""
    resp = await client.post("/api/auth/passkey/login/options")
    assert resp.status_code == 200
    assert not resp.json()["options"].get("allowCredentials")


async def test_signup_options_needs_a_display_name(client):
    resp = await client.post(
        "/api/auth/passkey/signup/options", json={"display_name": "   "}
    )
    assert resp.status_code == 422


async def test_signup_options_rejects_a_bad_email(client):
    resp = await client.post(
        "/api/auth/passkey/signup/options",
        json={"display_name": "Nobody", "email": "not-an-email"},
    )
    assert resp.status_code == 422


# ── ceremony state ───────────────────────────────────────────────────────────


async def test_unknown_ceremony_is_rejected(client):
    headers = await _register(client)
    resp = await client.post(
        "/api/auth/passkey/register/verify",
        headers=headers,
        json={"ceremony_id": "0" * 32, "credential": {"id": "x"}},
    )
    assert resp.status_code == 401


async def test_ceremony_is_single_use(client):
    """The stored challenge is burned on read, so a replay finds nothing —
    even before the credential itself is looked at."""
    headers = await _register(client)
    opts = await client.post("/api/auth/passkey/register/options", headers=headers)
    ceremony_id = opts.json()["ceremony_id"]

    payload = {"ceremony_id": ceremony_id, "credential": {"id": "garbage"}}
    first = await client.post(
        "/api/auth/passkey/register/verify", headers=headers, json=payload
    )
    assert first.status_code == 401  # bad credential, but the ceremony existed

    second = await client.post(
        "/api/auth/passkey/register/verify", headers=headers, json=payload
    )
    assert second.status_code == 401
    assert "unknown or expired" in second.json()["detail"].lower()


async def test_login_ceremony_cannot_be_spent_on_registration(client):
    """Scopes keep the flows apart: a challenge issued for login is stored
    under a different key and is invisible to the registration endpoint."""
    headers = await _register(client)
    opts = await client.post("/api/auth/passkey/login/options")
    ceremony_id = opts.json()["ceremony_id"]

    resp = await client.post(
        "/api/auth/passkey/register/verify",
        headers=headers,
        json={"ceremony_id": ceremony_id, "credential": {"id": "x"}},
    )
    assert resp.status_code == 401
    assert "unknown or expired" in resp.json()["detail"].lower()


async def test_malformed_credential_is_401_not_500(client):
    """py_webauthn raises a whole family of parse errors that share no base
    class — `InvalidJSONStructure`, `InvalidCBORData`, `UnsupportedAlgorithm`…
    The first version of this suite caught them by name and a missing `rawId`
    escaped as an unhandled 500 (2026-07-29). Anything past the library call is
    untrusted input, so anything it raises is a client error."""
    headers = await _register(client, prefix="pk-junk")
    for junk in ({}, {"id": "x"}, {"rawId": "!!!not-base64!!!"}, {"rawId": "AAAA"}):
        opts = await client.post(
            "/api/auth/passkey/register/options", headers=headers
        )
        resp = await client.post(
            "/api/auth/passkey/register/verify",
            headers=headers,
            json={"ceremony_id": opts.json()["ceremony_id"], "credential": junk},
        )
        assert resp.status_code == 401, f"{junk} → {resp.status_code}"


async def test_login_with_unknown_credential_is_401(client):
    """Same answer as a bad signature — an unknown credential must not be
    distinguishable from an invalid one."""
    opts = await client.post("/api/auth/passkey/login/options")
    resp = await client.post(
        "/api/auth/passkey/login/verify",
        json={
            "ceremony_id": opts.json()["ceremony_id"],
            "credential": {"id": "bm9wZQ", "rawId": "bm9wZQ"},
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication failed"


# ── device list and unlink ───────────────────────────────────────────────────


async def test_list_shows_only_my_devices(client, session_maker):
    a = await _register(client, prefix="pk-a")
    b = await _register(client, prefix="pk-b")
    await _add_credential(session_maker, await _user_id(client, a), name="Mine")
    await _add_credential(session_maker, await _user_id(client, b), name="Theirs")

    resp = await client.get("/api/auth/passkey", headers=_with_step_up(a, await _step_up(client, a)))
    assert resp.status_code == 200
    names = [c["device_name"] for c in resp.json()]
    assert names == ["Mine"]


async def test_cannot_delete_someone_elses_device(client, session_maker):
    a = await _register(client, prefix="pk-x")
    b = await _register(client, prefix="pk-y")
    victim = await _add_credential(session_maker, await _user_id(client, b))

    resp = await client.delete(
        f"/api/auth/passkey/{victim}",
        headers=_with_step_up(a, await _step_up(client, a)),
    )
    assert resp.status_code == 404


async def test_delete_works_when_a_password_remains(client, session_maker):
    headers = await _register(client)
    cred_id = await _add_credential(session_maker, await _user_id(client, headers))

    resp = await client.delete(
        f"/api/auth/passkey/{cred_id}",
        headers=_with_step_up(headers, await _step_up(client, headers)),
    )
    assert resp.status_code == 204


async def test_cannot_delete_the_last_way_in(client, session_maker):
    """A passwordless account with one passkey has exactly one door. Removing
    it is not logging out — email is optional here, so there may be nothing to
    recover through."""
    headers = await _register(client, prefix="pk-lock")
    uid = await _user_id(client, headers)

    # Confirmation first, password removed after: this test is about the guard,
    # and a real passwordless account would confirm with its passkey — which
    # pytest cannot produce without an authenticator (see the Playwright spec).
    token = await _step_up(client, headers)

    async with session_maker() as db:
        user = await db.get(User, uid)
        user.password_hash = None
        await db.commit()

    cred_id = await _add_credential(session_maker, uid)
    resp = await client.delete(
        f"/api/auth/passkey/{cred_id}",
        headers=_with_step_up(headers, token),
    )
    assert resp.status_code == 409
    assert "last way to sign in" in resp.json()["detail"].lower()


async def test_second_device_makes_the_first_removable(client, session_maker):
    headers = await _register(client, prefix="pk-two")
    uid = await _user_id(client, headers)

    token = await _step_up(client, headers)  # while the password still exists

    async with session_maker() as db:
        user = await db.get(User, uid)
        user.password_hash = None
        await db.commit()

    first = await _add_credential(session_maker, uid, name="One")
    await _add_credential(session_maker, uid, name="Two")

    resp = await client.delete(
        f"/api/auth/passkey/{first}",
        headers=_with_step_up(headers, token),
    )
    assert resp.status_code == 204

    async with session_maker() as db:
        left = (
            await db.execute(
                select(WebAuthnCredential).where(WebAuthnCredential.user_id == uid)
            )
        ).scalars().all()
    assert len(left) == 1


async def test_device_kind_is_reported(client, session_maker):
    """Losing a hardware key and losing a synced credential are different
    events, so the list says which is which."""
    headers = await _register(client, prefix="pk-kind")
    uid = await _user_id(client, headers)

    async with session_maker() as db:
        db.add(
            WebAuthnCredential(
                user_id=uid,
                credential_id=uuid.uuid4().bytes,
                public_key=b"pk",
                transports=["usb", "nfc"],
                backed_up=False,
                device_name="YubiKey",
            )
        )
        await db.commit()

    resp = await client.get("/api/auth/passkey", headers=headers)
    assert resp.json()[0]["device_kind"] == "hardware_key"
