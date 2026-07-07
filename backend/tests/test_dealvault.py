async def test_list_messages_empty_seed(client, sender_headers, seed_deal):
    resp = await client.get(f"/api/deals/{seed_deal.id}/dealvault", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert "next_cursor" in body


async def _count_all_messages(client, headers, deal_id) -> int:
    cursor: str | None = None
    total = 0
    for _ in range(100):
        params: dict = {"limit": 100}
        if cursor:
            params["after"] = cursor
        resp = await client.get(
            f"/api/deals/{deal_id}/dealvault", headers=headers, params=params
        )
        body = resp.json()
        total += len(body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            break
    return total


async def test_create_message_appends(client, sender_headers, seed_deal):
    before_count = await _count_all_messages(client, sender_headers, seed_deal.id)

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "Hello from sender", "is_system": False},
    )
    assert resp.status_code == 201
    assert resp.json()["text"] == "Hello from sender"

    after_count = await _count_all_messages(client, sender_headers, seed_deal.id)
    assert after_count == before_count + 1


async def test_dealvault_forbidden_for_outsider(client, seed_deal):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": f"outsider-vault-{str(seed_deal.id)[:6]}@vimana.test",
            "password": "outsider-pass",
            "display_name": "Vault Outsider",
        },
    )
    if resp.status_code == 201:
        email = resp.json()["email"]
    else:
        email = f"outsider-vault-{str(seed_deal.id)[:6]}@vimana.test"

    login = await client.post(
        "/api/auth/login", json={"login": email, "password": "outsider-pass"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/deals/{seed_deal.id}/dealvault", headers=headers)
    assert resp.status_code == 403
