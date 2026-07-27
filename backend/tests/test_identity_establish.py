"""T3.12 pt.2 — establish identity + declare lost.

The property under test throughout: the server accepts a key only from someone
who can prove they control it, and only once. `import` used to take a bare npub
on trust, which under `D-KEY-IS-IDENTITY` meant anyone could claim anyone's
identity by pasting their public key.

Requires Redis (challenges live there) — the same dependency `token_blacklist`
already has.
"""
import time
import uuid

from sqlalchemy import select

from app.core.identity_proof import PURPOSE_ESTABLISH, proof_event_id
from app.core.keypair import generate_keypair, sign_event_id
from app.models.user import User
from tests.conftest import SEED_PASSWORD, unique_email

PASSWORD = SEED_PASSWORD


async def _fresh_user(client, prefix: str = "idn") -> tuple[str, dict[str, str]]:
    email = unique_email(prefix)
    reg = await client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Identity"},
    )
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": PASSWORD}
    )
    return email, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _sign(npub: str, nsec: str, challenge: str, created_at: int | None = None) -> dict:
    created_at = created_at if created_at is not None else int(time.time())
    event_id = proof_event_id(npub, PURPOSE_ESTABLISH, challenge, created_at)
    return {
        "npub_hex": npub,
        "challenge": challenge,
        "created_at": created_at,
        "sig": sign_event_id(event_id, nsec),
    }


async def _challenge(client, headers) -> str:
    resp = await client.post("/api/me/identity/challenge", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["challenge"]


async def _establish(client, headers) -> tuple[str, str, dict]:
    """Full happy-path transition. Returns (nsec, npub, response json)."""
    nsec, npub = generate_keypair()
    challenge = await _challenge(client, headers)
    resp = await client.post(
        "/api/me/identity/establish", headers=headers, json=_sign(npub, nsec, challenge)
    )
    return nsec, npub, resp


# ── establish ────────────────────────────────────────────────────────────────


async def test_establish_takes_ownership(client, session_maker):
    email, headers = await _fresh_user(client)
    _, npub, resp = await _establish(client, headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["npub"] == npub
    assert body["identity_established"] is True
    assert body["key_lost"] is False

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
    # The service key is gone: nothing left that the platform can sign with.
    assert user.nsec_encrypted is None
    assert user.nsec_nonce is None
    assert user.key_self_custody is True


async def test_establish_replaces_the_service_key(client, session_maker):
    email, headers = await _fresh_user(client)
    async with session_maker() as db:
        before = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one().nostr_pubkey

    _, npub, resp = await _establish(client, headers)
    assert resp.status_code == 200
    assert npub != before, "identity must be a new key, not the promoted service one"


async def test_establish_rejects_unsigned_claim(client):
    """The old `import` hole: a bare npub with nothing to back it."""
    _, headers = await _fresh_user(client)
    _, victim_npub = generate_keypair()
    challenge = await _challenge(client, headers)

    resp = await client.post(
        "/api/me/identity/establish",
        headers=headers,
        json={
            "npub_hex": victim_npub,
            "challenge": challenge,
            "created_at": int(time.time()),
            "sig": "0" * 128,
        },
    )
    assert resp.status_code == 401


async def test_establish_rejects_signature_from_another_key(client):
    _, headers = await _fresh_user(client)
    other_nsec, _ = generate_keypair()
    _, claimed_npub = generate_keypair()
    challenge = await _challenge(client, headers)

    payload = _sign(claimed_npub, other_nsec, challenge)
    resp = await client.post(
        "/api/me/identity/establish", headers=headers, json=payload
    )
    assert resp.status_code == 401


async def test_challenge_is_single_use(client):
    _, headers = await _fresh_user(client)
    nsec, npub = generate_keypair()
    challenge = await _challenge(client, headers)

    first = await client.post(
        "/api/me/identity/establish", headers=headers, json=_sign(npub, nsec, challenge)
    )
    assert first.status_code == 200

    # Same signed payload again — a captured proof must not replay.
    second = await client.post(
        "/api/me/identity/establish", headers=headers, json=_sign(npub, nsec, challenge)
    )
    assert second.status_code == 409  # identity already established


async def test_replayed_challenge_on_a_fresh_account(client):
    """Burned nonce, different account: must fail on the challenge, not later."""
    _, headers_a = await _fresh_user(client, "idn-a")
    challenge = await _challenge(client, headers_a)
    nsec, npub = generate_keypair()
    await client.post(
        "/api/me/identity/establish", headers=headers_a, json=_sign(npub, nsec, challenge)
    )

    _, headers_b = await _fresh_user(client, "idn-b")
    nsec_b, npub_b = generate_keypair()
    resp = await client.post(
        "/api/me/identity/establish",
        headers=headers_b,
        json=_sign(npub_b, nsec_b, challenge),
    )
    assert resp.status_code == 401


async def test_stale_timestamp_rejected(client):
    _, headers = await _fresh_user(client)
    nsec, npub = generate_keypair()
    challenge = await _challenge(client, headers)

    payload = _sign(npub, nsec, challenge, created_at=int(time.time()) - 3600)
    resp = await client.post(
        "/api/me/identity/establish", headers=headers, json=payload
    )
    assert resp.status_code == 401


async def test_cannot_take_a_key_another_account_holds(client, seed_carrier):
    _, headers = await _fresh_user(client)
    challenge = await _challenge(client, headers)
    # Sign with a key we control, but claim the seed carrier's npub — the
    # signature will not match, so this lands on 401 before the uniqueness
    # check. Claiming it *with* its own key is impossible without that nsec,
    # which is exactly the protection.
    nsec, _ = generate_keypair()
    payload = _sign(seed_carrier.nostr_pubkey, nsec, challenge)
    resp = await client.post(
        "/api/me/identity/establish", headers=headers, json=payload
    )
    assert resp.status_code == 401


async def test_same_key_cannot_serve_two_accounts(client):
    """One key, one identity. Reachable only when the caller genuinely holds
    the key — hence the valid signature on both attempts."""
    _, headers_a = await _fresh_user(client, "idn-dup-a")
    nsec, npub = generate_keypair()
    challenge_a = await _challenge(client, headers_a)
    first = await client.post(
        "/api/me/identity/establish",
        headers=headers_a,
        json=_sign(npub, nsec, challenge_a),
    )
    assert first.status_code == 200

    _, headers_b = await _fresh_user(client, "idn-dup-b")
    challenge_b = await _challenge(client, headers_b)
    second = await client.post(
        "/api/me/identity/establish",
        headers=headers_b,
        json=_sign(npub, nsec, challenge_b),
    )
    assert second.status_code == 409
    assert "another account" in second.json()["detail"].lower()


async def test_challenge_refused_once_established(client):
    _, headers = await _fresh_user(client)
    _, _, resp = await _establish(client, headers)
    assert resp.status_code == 200

    again = await client.post("/api/me/identity/challenge", headers=headers)
    assert again.status_code == 409


async def test_container_survives_the_transition(client, session_maker):
    """pt.2b — the document must remain readable by its owner afterwards.

    Before: the container's AES key *was* the service nsec, which `establish`
    destroys — nobody could ever open it again. Now the blob moves to a random
    content key wrapped to the new identity.
    """
    from app.core.threshold import nip04_decrypt
    from app.core.verification import encrypt_container, sha256_hex
    from app.models.verification import IdentityContainer
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    document = b"passport-scan-bytes"
    email, headers = await _fresh_user(client, "idn-cnt")

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        nonce, ct = encrypt_container(user, document)
        container = IdentityContainer(
            owner_id=user.id,
            blob_encrypted=ct,
            blob_nonce=nonce,
            # Must be the real hash of the plaintext — that is what upload
            # stores (`_make_container`), and what the re-wrap self-check
            # verifies against.
            doc_hash=sha256_hex(document),
        )
        db.add(container)
        await db.commit()
        container_id = container.id

    new_nsec, new_npub = generate_keypair()
    challenge = await _challenge(client, headers)
    resp = await client.post(
        "/api/me/identity/establish",
        headers=headers,
        json=_sign(new_npub, new_nsec, challenge),
    )
    assert resp.status_code == 200, resp.text

    async with session_maker() as db:
        stored = await db.get(IdentityContainer, container_id)
        await db.refresh(stored)
        assert stored.key_envelope, "container was not re-wrapped"
        assert stored.key_envelope_sender_pubkey

        # The owner opens it with the key the server never saw.
        content_key = nip04_decrypt(
            stored.key_envelope, new_nsec, stored.key_envelope_sender_pubkey
        )
        plaintext = AESGCM(content_key).decrypt(
            bytes(stored.blob_nonce), bytes(stored.blob_encrypted), None
        )
    assert plaintext == document


async def test_establish_still_blocked_by_e2e_messages(
    client, session_maker, seed_deal
):
    """The one case the server cannot fix on its own: a read package is
    ECDH'd against the *message author's* key, and re-addressing it to a new
    identity would need that author's private key."""
    from app.models.deal import Deal, DealVaultMessage

    email, headers = await _fresh_user(client, "idn-e2e")
    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        # A deal of this user's own, reusing the seed order/trip rows. The seed
        # deal itself is shared across the session and must not be mutated.
        own_deal = Deal(
            order_id=seed_deal.order_id,
            trip_id=seed_deal.trip_id,
            sender_id=user.id,
            carrier_id=seed_deal.carrier_id,
        )
        db.add(own_deal)
        await db.flush()
        db.add(
            DealVaultMessage(
                deal_id=own_deal.id,
                sender_id=user.id,
                is_e2e=True,
                read_packages={"sender": "ct?iv=iv"},
            )
        )
        await db.commit()

    nsec, npub = generate_keypair()
    challenge = await _challenge(client, headers)
    resp = await client.post(
        "/api/me/identity/establish", headers=headers, json=_sign(npub, nsec, challenge)
    )
    assert resp.status_code == 409
    assert "end-to-end" in resp.json()["detail"].lower()


async def test_failed_rewrap_leaves_the_account_untouched(
    client, session_maker, monkeypatch
):
    """The safety property behind doing this inline: if the re-encryption
    cannot be proven, nothing changes — the service key survives and the
    document stays readable."""
    from app.core.verification import encrypt_container
    from app.models.verification import IdentityContainer

    email, headers = await _fresh_user(client, "idn-fail")
    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        nonce, ct = encrypt_container(user, b"doc")
        db.add(
            IdentityContainer(
                owner_id=user.id,
                blob_encrypted=ct,
                blob_nonce=nonce,
                # Deliberately not the hash of the document: stands in for a
                # container the re-wrap cannot prove readable.
                doc_hash=uuid.uuid4().hex * 2,
            )
        )
        await db.commit()
        before_npub = user.nostr_pubkey

    nsec, npub = generate_keypair()
    challenge = await _challenge(client, headers)
    resp = await client.post(
        "/api/me/identity/establish", headers=headers, json=_sign(npub, nsec, challenge)
    )
    assert resp.status_code == 500
    assert "untouched" in resp.json()["detail"].lower()

    async with session_maker() as db:
        after = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
    assert after.nostr_pubkey == before_npub
    assert after.key_self_custody is False
    assert after.nsec_encrypted is not None


async def test_rewrap_is_idempotent(session_maker):
    """A retried transition must not double-encrypt the blob."""
    from app.core.keypair import generate_keypair as gen
    from app.core.verification import encrypt_container, rewrap_container_to_identity
    from app.models.verification import IdentityContainer

    email = unique_email("idn-idem")
    async with session_maker() as db:
        from app.core.keypair import encrypt_nsec

        nsec_hex, npub_hex = gen()
        nsec_nonce, nsec_ct = encrypt_nsec(nsec_hex)
        user = User(
            email=email,
            password_hash=None,
            display_name="Idem",
            nostr_pubkey=npub_hex,
            nsec_encrypted=nsec_ct,
            nsec_nonce=nsec_nonce,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        nonce, ct = encrypt_container(user, b"doc")
        container = IdentityContainer(
            owner_id=user.id,
            blob_encrypted=ct,
            blob_nonce=nonce,
            doc_hash=uuid.uuid4().hex * 2,
        )
        db.add(container)
        await db.commit()

        _, new_npub = gen()
        rewrap_container_to_identity(
            container,
            old_nsec_hex=nsec_hex,
            old_npub_hex=npub_hex,
            new_npub_hex=new_npub,
        )
        first_blob = bytes(container.blob_encrypted)
        first_envelope = container.key_envelope

        rewrap_container_to_identity(
            container,
            old_nsec_hex=nsec_hex,
            old_npub_hex=npub_hex,
            new_npub_hex=new_npub,
        )

    assert bytes(container.blob_encrypted) == first_blob
    assert container.key_envelope == first_envelope


# ── declare lost ─────────────────────────────────────────────────────────────


async def test_declare_lost_requires_an_identity(client):
    _, headers = await _fresh_user(client)
    resp = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"password": PASSWORD}
    )
    assert resp.status_code == 409


async def test_declare_lost_wrong_password(client):
    _, headers = await _fresh_user(client)
    await _establish(client, headers)

    resp = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"password": "nope"}
    )
    assert resp.status_code == 401


async def test_declare_lost_marks_account_and_is_idempotent(client):
    _, headers = await _fresh_user(client)
    await _establish(client, headers)

    first = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"password": PASSWORD}
    )
    assert first.status_code == 200
    assert first.json()["key_lost"] is True

    second = await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"password": PASSWORD}
    )
    assert second.status_code == 200
    assert second.json()["key_lost"] is True


async def test_lost_key_cannot_publish_a_trip(client):
    """A dead identity must not sit opposite a counterparty: it cannot sign a
    single record any more."""
    from datetime import datetime, timedelta, timezone

    email = unique_email("idn-dead")
    await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Dead",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await _establish(client, headers)
    await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"password": PASSWORD}
    )

    resp = await client.post(
        "/api/trips",
        headers=headers,
        json={
            "origin": "Tbilisi",
            "destination": "Yerevan",
            "depart_at": (
                datetime.now(timezone.utc) + timedelta(days=7)
            ).isoformat(),
            "capacity": 3.0,
            "allowed_categories": ["documents"],
        },
    )
    assert resp.status_code == 403
    assert "lost" in resp.json()["detail"].lower()


async def test_status_reports_the_three_states(client):
    _, headers = await _fresh_user(client)

    before = await client.get("/api/me/keypair/status", headers=headers)
    assert before.json()["identity_established"] is False
    assert before.json()["key_lost"] is False

    await _establish(client, headers)
    after = await client.get("/api/me/keypair/status", headers=headers)
    assert after.json()["identity_established"] is True

    await client.post(
        "/api/me/identity/declare-lost", headers=headers, json={"password": PASSWORD}
    )
    dead = await client.get("/api/me/keypair/status", headers=headers)
    assert dead.json()["key_lost"] is True
