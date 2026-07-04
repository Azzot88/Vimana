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


async def test_create_invite_ttl_is_14_days(client, carrier_headers):
    from datetime import datetime, timezone
    resp = await client.post("/api/invites", headers=carrier_headers, json={})
    assert resp.status_code == 201
    expires_at = datetime.fromisoformat(resp.json()["expires_at"].replace("Z", "+00:00"))
    delta = expires_at - datetime.now(timezone.utc)
    days = delta.total_seconds() / 86400
    assert 13.9 < days <= 14.0


async def test_list_my_invites_returns_pending_status(client):
    email = unique_email("inv-owner")
    headers = await _register_and_login(client, email)

    create = await client.post("/api/invites", headers=headers, json={})
    token = create.json()["token"]

    resp = await client.get("/api/invites/mine", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    mine = [i for i in body if i["token"] == token]
    assert len(mine) == 1
    assert mine[0]["status"] == "pending"
    assert mine[0]["accepted_by_display_name"] is None


async def test_list_my_invites_reflects_accepted(client):
    owner_headers = await _register_and_login(client, unique_email("inv-o"))
    create = await client.post("/api/invites", headers=owner_headers, json={})
    token = create.json()["token"]

    friend_headers = await _register_and_login(client, unique_email("inv-friend"))
    accept = await client.post(f"/api/invites/{token}/accept", headers=friend_headers)
    assert accept.status_code == 200

    resp = await client.get("/api/invites/mine", headers=owner_headers)
    assert resp.status_code == 200
    mine = [i for i in resp.json() if i["token"] == token]
    assert len(mine) == 1
    assert mine[0]["status"] == "accepted"
    assert mine[0]["accepted_by_display_name"] is not None


async def test_list_my_invites_empty_for_new_user(client):
    headers = await _register_and_login(client, unique_email("inv-empty"))
    resp = await client.get("/api/invites/mine", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []
