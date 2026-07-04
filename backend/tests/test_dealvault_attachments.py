import hashlib


async def test_upload_attachment_computes_sha256_and_saves(client, sender_headers, seed_deal):
    msg_resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "message with attachment", "is_system": False},
    )
    assert msg_resp.status_code == 201
    msg_id = msg_resp.json()["id"]

    payload = b"hello vimana test attachment"
    expected_hash = hashlib.sha256(payload).hexdigest()

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("test.txt", payload, "text/plain")},
        data={"kind": "doc"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "doc"
    assert body["file_hash"] == expected_hash
    assert body["ipfs_cid"] is None


async def test_upload_attachment_rejects_invalid_kind(client, sender_headers, seed_deal):
    msg_resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "reject me", "is_system": False},
    )
    msg_id = msg_resp.json()["id"]

    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("x.bin", b"x", "application/octet-stream")},
        data={"kind": "bogus_kind"},
    )
    assert resp.status_code == 422


async def test_upload_attachment_wrong_deal_returns_404(client, sender_headers, seed_deal):
    msg_resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": "orphan", "is_system": False},
    )
    msg_id = msg_resp.json()["id"]

    import uuid as uuidlib
    fake_deal_id = uuidlib.uuid4()
    resp = await client.post(
        f"/api/deals/{fake_deal_id}/dealvault/messages/{msg_id}/attachments",
        headers=sender_headers,
        files={"file": ("x.bin", b"x", "application/octet-stream")},
        data={"kind": "doc"},
    )
    assert resp.status_code in (403, 404)
