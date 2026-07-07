import uuid as uuidlib


async def test_join_waitlist_success(client):
    email = f"wl-{uuidlib.uuid4().hex[:8]}@vimana.test"
    resp = await client.post(
        "/api/waitlist", json={"email": email, "name": "Test User", "source": "hero_cta"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert body["name"] == "Test User"
    assert body["source"] == "hero_cta"


async def test_join_waitlist_normalizes_email(client):
    prefix = uuidlib.uuid4().hex[:6]
    resp = await client.post(
        "/api/waitlist", json={"email": f"  UPPER-{prefix}@Vimana.Test  "}
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == f"upper-{prefix}@vimana.test"


async def test_join_waitlist_duplicate_returns_409(client):
    email = f"dup-{uuidlib.uuid4().hex[:8]}@vimana.test"
    first = await client.post("/api/waitlist", json={"email": email})
    assert first.status_code == 201
    second = await client.post("/api/waitlist", json={"email": email})
    assert second.status_code == 409


async def test_join_waitlist_invalid_email_returns_422(client):
    resp = await client.post("/api/waitlist", json={"email": "not-an-email"})
    assert resp.status_code == 422


async def test_list_waitlist_without_token_forbidden(client):
    resp = await client.get("/api/waitlist")
    assert resp.status_code == 403


async def test_list_waitlist_with_wrong_token_forbidden(client):
    resp = await client.get("/api/waitlist", headers={"X-Admin-Token": "wrong-token"})
    assert resp.status_code == 403


async def test_list_waitlist_with_correct_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-secret")
    email = f"list-{uuidlib.uuid4().hex[:8]}@vimana.test"
    await client.post("/api/waitlist", json={"email": email})

    resp = await client.get(
        "/api/waitlist", headers={"X-Admin-Token": "test-admin-secret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    emails = {e["email"] for e in body["items"]}
    assert email in emails
    assert "next_cursor" in body
