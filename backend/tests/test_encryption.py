"""T1.21 — at-rest AES-256-GCM encryption for DealVault messages."""
import base64
import os

import pytest
from sqlalchemy import text

from app.core import crypto


async def test_encrypt_decrypt_roundtrip():
    """Plain crypto layer roundtrip."""
    nonce, ct = crypto.encrypt("hello, мир! 🌍")
    assert nonce != ct
    assert isinstance(nonce, bytes)
    assert isinstance(ct, bytes)
    assert len(nonce) == 12
    assert crypto.decrypt(nonce, ct) == "hello, мир! 🌍"


async def test_encrypt_different_ciphertext_each_call():
    """Same plaintext → different ciphertext due to random nonce (semantic security)."""
    n1, c1 = crypto.encrypt("same text")
    n2, c2 = crypto.encrypt("same text")
    assert (n1, c1) != (n2, c2)


async def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MESSAGE_ENCRYPTION_KEY", raising=False)
    crypto.reset_key_cache()
    try:
        with pytest.raises(RuntimeError, match="MESSAGE_ENCRYPTION_KEY"):
            crypto.encrypt("no key")
    finally:
        # Restore for subsequent tests
        monkeypatch.setenv(
            "MESSAGE_ENCRYPTION_KEY",
            base64.b64encode(b"vimana-test-key-32-bytes-length!").decode(),
        )
        crypto.reset_key_cache()


async def test_bad_key_length_raises(monkeypatch):
    monkeypatch.setenv(
        "MESSAGE_ENCRYPTION_KEY", base64.b64encode(b"short").decode()
    )
    crypto.reset_key_cache()
    try:
        with pytest.raises(RuntimeError, match="32 bytes"):
            crypto.encrypt("bad key")
    finally:
        monkeypatch.setenv(
            "MESSAGE_ENCRYPTION_KEY",
            base64.b64encode(b"vimana-test-key-32-bytes-length!").decode(),
        )
        crypto.reset_key_cache()


async def test_message_stored_encrypted_in_db(
    client, carrier_headers, sender_headers, session_maker, seed_deal
):
    """POST a message → direct SQL shows bytes, not plaintext."""
    secret = "carrier will pick up at 3pm — do not disclose"
    resp = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": secret, "is_system": False},
    )
    assert resp.status_code == 201
    msg_id = resp.json()["id"]

    async with session_maker() as db:
        row = await db.execute(
            text(
                "SELECT text_ciphertext, text_nonce FROM deal_vault_messages "
                "WHERE id = :id"
            ),
            {"id": msg_id},
        )
        ct, nonce = row.one()
        assert ct is not None and nonce is not None
        assert isinstance(bytes(ct), bytes)
        # Plaintext must not appear anywhere in the ciphertext bytes.
        assert secret.encode("utf-8") not in bytes(ct)


async def test_message_roundtrip_via_api(
    client, carrier_headers, sender_headers, seed_deal
):
    """POST + GET returns the same plaintext. Walks pagination — seed_deal
    accumulates messages across the suite, so the new message can be past
    the first page (ASC-ordered)."""
    plaintext = "Привет, курьер! Готов к передаче."
    post = await client.post(
        f"/api/deals/{seed_deal.id}/dealvault/messages",
        headers=sender_headers,
        json={"text": plaintext, "is_system": False},
    )
    assert post.status_code == 201
    assert post.json()["text"] == plaintext

    texts: list[str] = []
    cursor: str | None = None
    for _ in range(50):  # generous cap for cursor walking
        url = f"/api/deals/{seed_deal.id}/dealvault?limit=100"
        if cursor:
            url += f"&after={cursor}"
        got = await client.get(url, headers=carrier_headers)
        assert got.status_code == 200
        body = got.json()
        texts.extend(m["text"] for m in body["items"] if m["text"])
        cursor = body.get("next_cursor")
        if not cursor:
            break
    assert plaintext in texts


async def test_system_message_encrypted(
    client, sender_headers, seed_deal, session_maker
):
    """Arbiter-opened system-message goes through the same encryption path."""
    from app.models.deal import DealVaultMessage

    async with session_maker() as db:
        msg = DealVaultMessage(
            deal_id=seed_deal.id,
            sender_id=None,
            text="⚖️ system: audit trail",
            is_system=True,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        assert msg.text_ciphertext is not None
        assert msg.text_nonce is not None
        # Property getter decrypts transparently
        assert msg.text == "⚖️ system: audit trail"
