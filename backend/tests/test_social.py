from tests.conftest import unique_email


async def _register_and_login(client, email: str, password: str = "invite-pass-1"):
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    assert reg.status_code == 201
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_create_invite(client, carrier_headers):
    resp = await client.post("/api/invites", headers=carrier_headers, json={})
    assert resp.status_code == 201
    body = resp.json()
    assert "token" in body
    assert "expires_at" in body


async def test_accept_invite_creates_two_way_connection(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    friend_headers = await _register_and_login(client, unique_email("friend"))

    accept = await client.post(f"/api/invites/{token}/accept", headers=friend_headers)
    assert accept.status_code == 200

    # Friend sees carrier in connections
    friend_conn = await client.get("/api/me/connections", headers=friend_headers)
    assert friend_conn.status_code == 200
    assert len(friend_conn.json()) >= 1

    # Carrier sees friend in connections
    carrier_conn = await client.get("/api/me/connections", headers=carrier_headers)
    assert carrier_conn.status_code == 200
    assert len(carrier_conn.json()) >= 1


async def test_accept_own_invite_forbidden(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    resp = await client.post(f"/api/invites/{token}/accept", headers=carrier_headers)
    assert resp.status_code == 400


async def test_accept_reused_invite_conflicts(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    first = await _register_and_login(client, unique_email("first"))
    ok = await client.post(f"/api/invites/{token}/accept", headers=first)
    assert ok.status_code == 200

    second = await _register_and_login(client, unique_email("second"))
    dup = await client.post(f"/api/invites/{token}/accept", headers=second)
    assert dup.status_code == 409


async def test_accept_unknown_invite_returns_404(client, carrier_headers):
    friend_headers = await _register_and_login(client, unique_email("nobody"))
    resp = await client.post(
        "/api/invites/nonexistent-token-value/accept", headers=friend_headers
    )
    assert resp.status_code == 404
