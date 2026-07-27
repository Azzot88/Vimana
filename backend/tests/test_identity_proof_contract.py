"""T3.12 — cross-language contract for the identity proof.

The browser signs a canonical NIP-01 event; the backend rebuilds it and checks
the signature. If the two serializations differ by one byte the signature is
over different data and `establish` answers 401 — which reads like "wrong key"
and sends you looking somewhere else entirely.

`EXPECTED` below is duplicated verbatim in
`frontend/src/test/identity.test.ts`. Neither side runs the other's code; both
are pinned to the same literal, so they cannot drift apart without one of these
tests going red.
"""
import hashlib
import json

from app.core.identity_proof import (
    PROOF_KIND,
    PURPOSE_ESTABLISH,
    build_proof_event,
    proof_event_id,
    verify_proof,
)
from app.core.keypair import generate_keypair, sign_event_id
from app.core.signing import compute_event_id

PUBKEY = "a" * 64
CHALLENGE = "cafebabe"
CREATED_AT = 1700000000

EXPECTED = (
    f'[0,"{PUBKEY}",{CREATED_AT},{PROOF_KIND},'
    f'[["challenge","{CHALLENGE}"],["purpose","{PURPOSE_ESTABLISH}"]],'
    f'"{PURPOSE_ESTABLISH}"]'
)


def test_canonical_serialization_matches_the_frontend():
    event = build_proof_event(PUBKEY, PURPOSE_ESTABLISH, CHALLENGE, CREATED_AT)
    serialized = json.dumps(
        [
            0,
            event["pubkey"],
            event["created_at"],
            event["kind"],
            event["tags"],
            event["content"],
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert serialized == EXPECTED


def test_event_id_is_sha256_of_that_exact_string():
    """Pins `compute_event_id` to the serialization above — otherwise the test
    over `EXPECTED` could pass while the id came from something else."""
    expected_id = hashlib.sha256(EXPECTED.encode("utf-8")).hexdigest()
    assert (
        proof_event_id(PUBKEY, PURPOSE_ESTABLISH, CHALLENGE, CREATED_AT) == expected_id
    )
    assert (
        compute_event_id(
            PUBKEY,
            CREATED_AT,
            PROOF_KIND,
            [["challenge", CHALLENGE], ["purpose", PURPOSE_ESTABLISH]],
            PURPOSE_ESTABLISH,
        )
        == expected_id
    )


def test_serialization_has_no_whitespace():
    assert " " not in EXPECTED
    assert "\n" not in EXPECTED


def test_roundtrip_signature_verifies():
    """The backend half of what the browser does, on the backend's own keys."""
    nsec, npub = generate_keypair()
    created_at = CREATED_AT
    event_id = proof_event_id(npub, PURPOSE_ESTABLISH, CHALLENGE, created_at)
    sig = sign_event_id(event_id, nsec)

    assert verify_proof(
        npub, PURPOSE_ESTABLISH, CHALLENGE, created_at, sig, now=created_at
    )


def test_proof_is_bound_to_its_purpose():
    """A proof minted for one purpose must not be replayable at another — the
    reason the purpose is inside the signed payload rather than alongside it."""
    nsec, npub = generate_keypair()
    event_id = proof_event_id(npub, PURPOSE_ESTABLISH, CHALLENGE, CREATED_AT)
    sig = sign_event_id(event_id, nsec)

    assert not verify_proof(
        npub, "vimana:identity:login", CHALLENGE, CREATED_AT, sig, now=CREATED_AT
    )


def test_proof_is_bound_to_its_challenge():
    nsec, npub = generate_keypair()
    event_id = proof_event_id(npub, PURPOSE_ESTABLISH, CHALLENGE, CREATED_AT)
    sig = sign_event_id(event_id, nsec)

    assert not verify_proof(
        npub, PURPOSE_ESTABLISH, "deadbeef", CREATED_AT, sig, now=CREATED_AT
    )
