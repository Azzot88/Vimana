"""T2.3 — threshold 2-of-3 e2e vault message + arbiter reveal."""
from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.threshold import nip44_encrypt
from tests.conftest import make_account


def _make_e2e_payload(
    sender_nsec: str,
    sender_npub: str,
    carrier_npub: str,
    arbiter_npub: str,
) -> dict:
    """Simulate what the browser client will produce.

    We stub SSS by using three distinct 33-byte "share" payloads; the real
    Shamir combine is verified via the frontend lib. Backend only stores and,
    on arbiter reveal, NIP-04 decrypts the arbiter's wrapped share — it doesn't
    interpret the plaintext bytes.
    """
    session_key = os.urandom(32)
    share_sender = b"\x01" + session_key
    share_carrier = b"\x02" + session_key
    share_arbiter = b"\x03" + session_key
    fake_ct = b"CIPHER-" + os.urandom(24)
    fake_nonce = os.urandom(12)
    return {
        "ciphertext": base64.b64encode(fake_ct).decode("ascii"),
        "nonce": base64.b64encode(fake_nonce).decode("ascii"),
        "wrapped_shares": {
            "sender": nip44_encrypt(share_sender, sender_nsec, sender_npub),
            "carrier": nip44_encrypt(share_carrier, sender_nsec, carrier_npub),
            "arbiter": nip44_encrypt(share_arbiter, sender_nsec, arbiter_npub),
        },
        "read_packages": {
            "sender": nip44_encrypt(session_key, sender_nsec, sender_npub),
            "carrier": nip44_encrypt(session_key, sender_nsec, carrier_npub),
        },
    }


@pytest.fixture
async def _e2e_deal(client, session_maker):
    """Fresh carrier + sender + matched deal, plus platform arbiter with
    ARBITER_USER_ID env pointing at them. Returns npubs for the three parties."""
    from tests.conftest import SEED_PASSWORD, unique_email

    # Sender
    s_email = unique_email("e2e-s")
    await make_account({"email": s_email, "password": SEED_PASSWORD, "display_name": "E2eS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}
    s_status = await client.get("/api/me/keypair/status", headers=s_headers)
    sender_npub = s_status.json()["npub"]
    # The sender stays custodial here — the point of this suite is the
    # server-mediated path. The test needs their service nsec to NIP-04-encrypt
    # on their behalf, and reads it the way the platform does (T3.12: `export`
    # is gone, it handed users a key that was never theirs).
    from tests.conftest import service_nsec_for_email

    sender_nsec = await service_nsec_for_email(session_maker, s_email)

    # Carrier
    c_email = unique_email("e2e-c")
    await make_account({
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "E2eC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}
    c_status = await client.get("/api/me/keypair/status", headers=c_headers)
    carrier_npub = c_status.json()["npub"]

    # Arbiter — role=arbiter user. Bootstrap via direct DB row + env pointer.
    from sqlalchemy import update

    from app.core.keypair import encrypt_nsec, generate_keypair
    from app.models.user import User
    from app.core.security import hash_password

    arb_nsec, arb_npub = generate_keypair()
    arb_nonce, arb_ct = encrypt_nsec(arb_nsec)
    async with session_maker() as db:
        arbiter = User(
            email=unique_email("arb"),
            password_hash=hash_password(SEED_PASSWORD),
            display_name="Arb",
            roles=["arbiter"],
            nostr_pubkey=arb_npub,
            nsec_encrypted=arb_ct,
            nsec_nonce=arb_nonce,
            key_self_custody=False,
        )
        db.add(arbiter)
        await db.commit()
        await db.refresh(arbiter)
        arbiter_id = arbiter.id

    os.environ["ARBITER_USER_ID"] = str(arbiter_id)

    # Trip + match.
    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "TE2",
            "destination": "END",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "capacity": 2.0,
            "allowed_categories": ["document"],
        },
    )
    trip_id = trip.json()["id"]
    match = await client.post(
        "/api/deals/match",
        headers=s_headers,
        json={
            "trip_id": trip_id,
            "order": {
                "recipient_contact": "+10000004444",
                "origin": "TE2",
                "destination": "END",
                "category": "document",
                "declared_value": 40.0,
            },
        },
    )
    deal_id = match.json()["id"]

    # Arbiter login for later use.
    a_login = await client.post(
        "/api/auth/login",
        json={"login": arbiter.email, "password": SEED_PASSWORD},
    )
    a_headers = {"Authorization": f"Bearer {a_login.json()['access_token']}"}

    yield {
        "sender_headers": s_headers,
        "carrier_headers": c_headers,
        "arbiter_headers": a_headers,
        "sender_nsec": sender_nsec,
        "sender_npub": sender_npub,
        "carrier_npub": carrier_npub,
        "arbiter_npub": arb_npub,
        "arbiter_nsec": arb_nsec,
        "deal_id": deal_id,
    }

    os.environ.pop("ARBITER_USER_ID", None)


async def test_arbiter_info_reports_platform_pubkey(client, _e2e_deal):
    d = _e2e_deal
    resp = await client.get("/api/threshold/arbiter-info", headers=d["sender_headers"])
    assert resp.status_code == 200
    assert resp.json()["npub"] == d["arbiter_npub"]


async def test_arbiter_info_503_when_env_missing(client, _e2e_deal):
    d = _e2e_deal
    os.environ.pop("ARBITER_USER_ID", None)
    resp = await client.get("/api/threshold/arbiter-info", headers=d["sender_headers"])
    assert resp.status_code == 503


async def test_e2e_write_stores_blob_and_hides_text(client, _e2e_deal, session_maker):
    from sqlalchemy import select

    from app.models.deal import DealVaultMessage

    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload},
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["is_e2e"] is True
    assert body["text"] is None
    assert body["ciphertext_b64"] == payload["ciphertext"]
    assert body["nonce_b64"] == payload["nonce"]
    assert body["read_packages"]["sender"] == payload["read_packages"]["sender"]
    assert body["read_packages"]["carrier"] == payload["read_packages"]["carrier"]

    # DB check: server has ciphertext bytes, wrapped_shares JSON, no plaintext.
    async with session_maker() as db:
        result = await db.execute(
            select(DealVaultMessage).where(DealVaultMessage.id == body["id"])
        )
        msg = result.scalar_one()
        assert msg.is_e2e is True
        assert msg.wrapped_shares.keys() == {"sender", "carrier", "arbiter"}
        assert msg.text is None  # property returns None for e2e


async def test_e2e_and_text_are_mutually_exclusive(client, _e2e_deal):
    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload, "text": "also plaintext"},
    )
    assert resp.status_code == 422
    assert "mutually exclusive" in resp.json()["detail"].lower()


async def test_e2e_payload_shape_validated(client, _e2e_deal):
    d = _e2e_deal
    resp = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": {"ciphertext": "x", "nonce": "y"}},  # missing shares
    )
    assert resp.status_code == 422


async def test_reveal_my_share_returns_envelope(client, _e2e_deal):
    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    write = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload},
    )
    msg_id = write.json()["id"]

    # Sender reveals sender share.
    r = await client.post(
        f"/api/threshold/dealvault/messages/{msg_id}/reveal-my-share",
        headers=d["sender_headers"],
    )
    assert r.status_code == 200
    assert r.json()["role"] == "sender"
    assert r.json()["envelope"] == payload["wrapped_shares"]["sender"]

    # Carrier reveals carrier share.
    r2 = await client.post(
        f"/api/threshold/dealvault/messages/{msg_id}/reveal-my-share",
        headers=d["carrier_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["role"] == "carrier"
    assert r2.json()["envelope"] == payload["wrapped_shares"]["carrier"]


async def test_reveal_my_share_forbidden_for_third_party(client, _e2e_deal):
    """A user not in the deal cannot fetch its shares."""
    from tests.conftest import SEED_PASSWORD, unique_email

    d = _e2e_deal
    payload = _make_e2e_payload(d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"])
    write = await client.post(
        f"/api/deals/{d['deal_id']}/dealvault/messages",
        headers=d["sender_headers"],
        json={"e2e_payload": payload},
    )
    msg_id = write.json()["id"]

    outsider_email = unique_email("outs")
    await make_account({
            "email": outsider_email,
            "password": SEED_PASSWORD,
            "display_name": "Out",
        },
    )
    login = await client.post(
        "/api/auth/login",
        json={"login": outsider_email, "password": SEED_PASSWORD},
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.post(
        f"/api/threshold/dealvault/messages/{msg_id}/reveal-my-share",
        headers=hdr,
    )
    assert r.status_code == 403


async def test_arbiter_reveal_returns_unwrapped_shares_with_audit(
    client, _e2e_deal, session_maker
):
    from sqlalchemy import select

    from app.models.deal import DealEvent, DealEventType

    d = _e2e_deal

    # Write two e2e messages.
    payloads = []
    for _ in range(2):
        p = _make_e2e_payload(
            d["sender_nsec"], d["sender_npub"], d["carrier_npub"], d["arbiter_npub"]
        )
        r = await client.post(
            f"/api/deals/{d['deal_id']}/dealvault/messages",
            headers=d["sender_headers"],
            json={"e2e_payload": p},
        )
        assert r.status_code == 201, r.json()
        payloads.append(p)

    # Open a dispute (participant-initiated) so arbiter-reveal precondition is met.
    disp = await client.post(
        f"/api/deals/{d['deal_id']}/dispute",
        headers=d["sender_headers"],
        json={"reason": "test"},
    )
    assert disp.status_code == 201, disp.json()

    reveal = await client.post(
        f"/api/threshold/disputes/{d['deal_id']}/arbiter-reveal",
        headers=d["arbiter_headers"],
    )
    assert reveal.status_code == 200, reveal.json()
    body = reveal.json()
    assert len(body["revealed"]) == 2
    for entry in body["revealed"]:
        # Unwrapped share is 33 bytes (our fake role-tag + 32-byte "session_key").
        share = base64.b64decode(entry["arbiter_share_b64"])
        assert len(share) == 33
        assert share[0] == 3  # arbiter role tag from _make_e2e_payload

    # Audit event recorded (arbiter_opened with kind=arbiter_share_revealed).
    async with session_maker() as db:
        rows = await db.execute(
            select(DealEvent).where(
                DealEvent.deal_id == d["deal_id"],
                DealEvent.event_type == DealEventType.arbiter_opened,
            )
        )
        arbiter_events = list(rows.scalars())
        assert any(
            (e.payload or {}).get("kind") == "arbiter_share_revealed"
            for e in arbiter_events
        )


async def test_arbiter_reveal_requires_arbiter_role(client, _e2e_deal):
    d = _e2e_deal
    resp = await client.post(
        f"/api/threshold/disputes/{d['deal_id']}/arbiter-reveal",
        headers=d["sender_headers"],
    )
    assert resp.status_code == 403


async def test_nip04_roundtrip_correctness():
    """Sanity: NIP-04 encrypt→decrypt is symmetric on our helpers."""
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt, nip44_encrypt

    a_nsec, a_npub = generate_keypair()
    b_nsec, b_npub = generate_keypair()
    payload = b"session-key-abc-123-XYZ"
    ct = nip44_encrypt(payload, a_nsec, b_npub)
    assert nip44_decrypt(ct, b_nsec, a_npub) == payload


# ── T_KEYS.1 — NIP-44 v2 ─────────────────────────────────────────────────────


def test_nip44_round_trip_both_directions():
    """ECDH is symmetric, so either side derives the same conversation key."""
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt, nip44_encrypt

    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    secret = "сессионный ключ и немного текста".encode()

    assert nip44_decrypt(nip44_encrypt(secret, a_priv, b_pub), b_priv, a_pub) == secret
    assert nip44_decrypt(nip44_encrypt(secret, b_priv, a_pub), a_priv, b_pub) == secret


@pytest.mark.parametrize(
    "unpadded,padded",
    # The schedule from the NIP-44 spec. Pinned as a table because it is an
    # interop contract: a frontend padding to different buckets produces
    # payloads this backend rejects, and the failure would look like a key
    # problem rather than an arithmetic one.
    [(16, 32), (32, 32), (33, 64), (65, 96), (100, 128), (200, 224), (250, 256),
     (256, 256), (257, 320), (320, 320), (383, 384), (384, 384), (400, 448),
     (515, 640), (1020, 1024)],
)
def test_nip44_padding_schedule(unpadded, padded):
    from app.core.threshold import _nip44_padded_len

    assert _nip44_padded_len(unpadded) == padded


def test_nip44_hides_length_within_a_bucket():
    """Two different plaintexts of nearby length must be indistinguishable by
    size. Without padding, "да" and "нет" are told apart by the ciphertext
    alone — which for a vault of negotiations is a real leak."""
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_encrypt

    a_priv, _ = generate_keypair()
    _, b_pub = generate_keypair()
    short = len(nip44_encrypt(b"yes", a_priv, b_pub))
    longer = len(nip44_encrypt(b"no, and here is why not", a_priv, b_pub))
    assert short == longer


def test_nip44_rejects_a_tampered_payload():
    """The reason for the whole migration: NIP-04 had no MAC, so a modified
    envelope decrypted to garbage and nothing distinguished that from a wrong
    key. Here it is refused, and refused before decryption."""
    import base64

    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt, nip44_encrypt

    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    raw = bytearray(base64.b64decode(nip44_encrypt(b"authentic message", a_priv, b_pub)))
    raw[40] ^= 0x01  # one bit inside the ciphertext

    with pytest.raises(HTTPException) as exc:
        nip44_decrypt(base64.b64encode(bytes(raw)).decode(), b_priv, a_pub)
    assert exc.value.status_code == 422


def test_nip44_rejects_the_wrong_reader():
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt, nip44_encrypt

    a_priv, a_pub = generate_keypair()
    _, b_pub = generate_keypair()
    stranger_priv, _ = generate_keypair()

    with pytest.raises(HTTPException):
        nip44_decrypt(nip44_encrypt(b"not for you", a_priv, b_pub), stranger_priv, a_pub)


# ── T_TEST.10 — the paths that refuse ─────────────────────────────────────
#
# Mutation testing put 112 of this module's 144 survivors in three places:
# `E2EPayload.__init__`, `nip44_decrypt`, and the padding pair. All three parse
# bytes chosen by somebody else, and not one of their rejections was reachable
# by the suite — everything above hands them well-formed input, so deleting a
# check changed nothing any test noticed.
#
# For input an attacker supplies, the refusals are not error handling wrapped
# around the feature. They are the feature.


def _valid_blob() -> dict:
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_encrypt

    priv, pub = generate_keypair()
    share = nip44_encrypt(b"a share", priv, pub)
    return {
        "ciphertext": base64.b64encode(b"ciphertext").decode(),
        "nonce": base64.b64encode(b"0" * 12).decode(),
        "wrapped_shares": {"sender": share, "carrier": share, "arbiter": share},
        "read_packages": {"sender": share, "carrier": share},
    }


def _drop(mapping: dict, key: str) -> dict:
    return {k: v for k, v in mapping.items() if k != key}


def _short_payload() -> str:
    """Valid base64, correct version byte, one byte below the 97-byte floor."""
    from app.core.threshold import NIP44_VERSION

    return base64.b64encode(bytes([NIP44_VERSION]) + b"\x00" * 95).decode()


def _wrong_version() -> str:
    from app.core.threshold import NIP44_VERSION

    return base64.b64encode(bytes([NIP44_VERSION + 1]) + b"\x00" * 100).decode()


def test_e2e_payload_accepts_a_well_formed_blob():
    from app.core.threshold import E2EPayload

    E2EPayload(_valid_blob())


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(lambda b: "a string, not an object", id="not-an-object"),
        pytest.param(lambda b: _drop(b, "ciphertext"), id="no-ciphertext"),
        pytest.param(lambda b: {**b, "nonce": 42}, id="nonce-not-a-string"),
        pytest.param(lambda b: {**b, "wrapped_shares": []}, id="shares-not-an-object"),
        pytest.param(
            lambda b: {**b, "wrapped_shares": _drop(b["wrapped_shares"], "arbiter")},
            id="no-share-for-the-arbiter",
        ),
        pytest.param(
            lambda b: {**b, "wrapped_shares": {**b["wrapped_shares"], "spare": "x"}},
            id="a-fourth-shareholder",
        ),
        pytest.param(
            lambda b: {**b, "read_packages": _drop(b["read_packages"], "carrier")},
            id="no-read-package-for-the-carrier",
        ),
        pytest.param(
            lambda b: {**b, "wrapped_shares": {**b["wrapped_shares"], "sender": 1}},
            id="share-not-a-string",
        ),
        pytest.param(
            lambda b: {**b, "wrapped_shares": {**b["wrapped_shares"], "sender": "!!!!"}},
            id="share-not-base64",
        ),
        pytest.param(
            lambda b: {
                **b,
                "wrapped_shares": {**b["wrapped_shares"], "sender": _short_payload()},
            },
            id="share-too-short-to-be-nip44",
        ),
        pytest.param(
            lambda b: {
                **b,
                "wrapped_shares": {**b["wrapped_shares"], "sender": _wrong_version()},
            },
            id="share-of-another-version",
        ),
    ],
)
def test_e2e_payload_refuses_one_thing_wrong(break_it):
    """One malformed field at a time, so a passing case cannot hide behind
    another. The shape is the only thing the server can judge — the contents
    are sealed to everyone but the recipient — which makes these checks the
    entire defence the endpoint has."""
    from app.core.threshold import E2EPayload

    with pytest.raises(HTTPException) as refused:
        E2EPayload(break_it(_valid_blob()))
    assert refused.value.status_code == 422


def test_to_blob_refuses_base64_it_cannot_decode():
    """`__init__` only asks whether these are strings; `to_blob` is where they
    are read. A blob can therefore be accepted and still fail here."""
    from app.core.threshold import E2EPayload

    payload = E2EPayload({**_valid_blob(), "ciphertext": "abc"})
    with pytest.raises(HTTPException) as refused:
        payload.to_blob()
    assert refused.value.status_code == 422


@pytest.mark.parametrize(
    "payload,reason",
    [
        ("#anything", "a NIP-04 envelope, which this version cannot read"),
        ("not base64 at all!", "not base64"),
        ("", "empty"),
    ],
)
def test_nip44_decrypt_refuses_malformed_input(payload, reason):
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt

    priv, _ = generate_keypair()
    _, pub = generate_keypair()
    with pytest.raises(HTTPException) as refused:
        nip44_decrypt(payload, priv, pub)
    assert refused.value.status_code == 422, reason


def test_nip44_decrypt_refuses_a_payload_below_the_floor():
    """Version + nonce + mac is 97 bytes before a single byte of message. Below
    that the slices still succeed — they just quietly overlap — so the length
    has to be checked rather than inferred."""
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt

    priv, _ = generate_keypair()
    _, pub = generate_keypair()
    with pytest.raises(HTTPException) as refused:
        nip44_decrypt(_short_payload(), priv, pub)
    assert refused.value.status_code == 422


def test_nip44_decrypt_refuses_an_unknown_version():
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_decrypt

    priv, _ = generate_keypair()
    _, pub = generate_keypair()
    with pytest.raises(HTTPException) as refused:
        nip44_decrypt(_wrong_version(), priv, pub)
    assert refused.value.status_code == 422


# ── padding: the arithmetic on both sides ─────────────────────────────────


@pytest.mark.parametrize("size", [1, 2, 31, 32, 33, 100, 1000, 65535])
def test_pad_then_unpad_returns_the_message(size):
    from app.core.threshold import _nip44_pad, _nip44_unpad

    message = os.urandom(size)
    assert _nip44_unpad(_nip44_pad(message)) == message


@pytest.mark.parametrize("size", [0, 65536])
def test_pad_refuses_lengths_outside_the_spec(size):
    from app.core.threshold import _nip44_pad

    with pytest.raises(HTTPException) as refused:
        _nip44_pad(b"\x00" * size)
    assert refused.value.status_code == 422


def test_padded_output_carries_its_own_length():
    from app.core.threshold import _nip44_pad, _nip44_padded_len

    padded = _nip44_pad(b"seven!!")
    assert int.from_bytes(padded[:2], "big") == 7
    assert len(padded) == _nip44_padded_len(7) + 2


@pytest.mark.parametrize(
    "padded,reason",
    [
        (b"", "nothing at all"),
        (b"\x00", "half a length prefix"),
        (b"\x00\x00" + b"\x00" * 32, "a declared length of zero"),
        (b"\x00\x40" + b"\x00" * 32, "declares more than it carries"),
        (b"\x00\x07" + b"\x00" * 40, "right message, wrong bucket"),
    ],
)
def test_unpad_refuses_padding_that_does_not_add_up(padded, reason):
    """The declared length and the total both have to agree with the schedule.

    Checking only the declaration would let a sender append bytes past the
    message that survive the round trip unnoticed — padding is a fixed-size
    envelope, so anything the schedule did not ask for is somebody's cargo.
    """
    from app.core.threshold import _nip44_unpad

    with pytest.raises(HTTPException) as refused:
        _nip44_unpad(padded)
    assert refused.value.status_code == 422, reason


# ── key derivation: what the round trip cannot see ────────────────────────


def test_message_keys_are_a_fixed_split_of_the_expansion():
    """Recomputed here from the spec rather than compared to itself.

    The round-trip tests above cannot see this at all: encryption and
    decryption call the same function, so a mutation that moves the boundary
    between the ChaCha key and the MAC key moves it identically on both sides
    and the message still comes back. What breaks is interoperability — our
    payloads stop being readable by any other NIP-44 client, and the suite
    stays green.
    """
    import hashlib
    import hmac

    from app.core.threshold import _nip44_message_keys

    conversation_key = bytes(range(32))
    nonce = bytes(range(32, 64))

    okm = b""
    block = b""
    for counter in (1, 2, 3):
        block = hmac.new(
            conversation_key, block + nonce + bytes([counter]), hashlib.sha256
        ).digest()
        okm += block

    assert _nip44_message_keys(conversation_key, nonce) == (
        okm[0:32],
        okm[32:44],
        okm[44:76],
    )


def test_conversation_key_uses_the_spec_salt():
    import hashlib
    import hmac

    from app.core.keypair import generate_keypair
    from app.core.threshold import nip04_shared_x, nip44_conversation_key

    a_priv, _ = generate_keypair()
    _, b_pub = generate_keypair()

    expected = hmac.new(
        b"nip44-v2", nip04_shared_x(a_priv, b_pub), hashlib.sha256
    ).digest()
    assert nip44_conversation_key(a_priv, b_pub) == expected


def test_envelope_keeps_the_legacy_shape_readable():
    """A bare string predates the dict and still sits in old rows, where the
    sender was always the message author — so the caller supplies it."""
    from app.core.threshold import envelope_parts

    assert envelope_parts("bare ciphertext", "author-pubkey") == (
        "bare ciphertext",
        "author-pubkey",
    )


def test_envelope_dict_carries_its_own_sender():
    from app.core.threshold import envelope_parts, make_envelope

    assert envelope_parts(make_envelope("ct", "service-key"), "author") == (
        "ct",
        "service-key",
    )


def test_a_dict_without_a_sender_does_not_borrow_the_default():
    """The default is for the legacy shape only. A dict that omits the sender is
    malformed, and answering `None` says so; substituting the message author
    would send the reader to complete an exchange with the wrong key."""
    from app.core.threshold import envelope_parts

    assert envelope_parts({"ct": "ct"}, "author") == ("ct", None)


def test_a_dict_without_a_ciphertext_yields_an_empty_string():
    """Empty rather than `None`, because the value is handed to base64 decoding
    downstream: `""` decodes to nothing, `None` raises `TypeError` from inside
    the crypto and arrives as a 500 instead of a refusal."""
    from app.core.threshold import envelope_parts

    assert envelope_parts({"sender_pubkey": "key"}, "author") == ("", "key")


def test_conversation_key_is_the_same_from_either_end():
    """ECDH's defining property, and the reason neither side has to be told
    which of them started the conversation."""
    from app.core.keypair import generate_keypair
    from app.core.threshold import nip44_conversation_key

    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()

    assert nip44_conversation_key(a_priv, b_pub) == nip44_conversation_key(b_priv, a_pub)
