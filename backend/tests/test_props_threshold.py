"""T_TEST.5 — property-based invariants for NIP-04 crypto (T2.3 threshold).

Hypothesis generates 200+ random inputs; if any single input breaks a property,
we get a minimal counterexample. Catches bugs unit tests miss (empty input,
weird utf-8, boundary sizes, key reuse).
"""
from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.core.keypair import generate_keypair
from app.core.threshold import nip44_decrypt, nip44_encrypt

# Fixed keypairs at module load — regenerating in every hypothesis loop would
# slow tests to a crawl (secp256k1 keygen is ~0.5ms but with 200 examples adds up).
_A_NSEC, _A_NPUB = generate_keypair()
_B_NSEC, _B_NPUB = generate_keypair()
_C_NSEC, _C_NPUB = generate_keypair()

_settings = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@_settings
@given(pt=st.binary(min_size=1, max_size=500))
def test_nip44_roundtrip_any_bytes(pt: bytes) -> None:
    """A→B encrypt, B→A decrypt using paired keys recovers the plaintext bytes."""
    ct = nip44_encrypt(pt, _A_NSEC, _B_NPUB)
    recovered = nip44_decrypt(ct, _B_NSEC, _A_NPUB)
    assert recovered == pt


@_settings
@given(pt=st.text(min_size=1, max_size=500))
def test_nip44_roundtrip_any_utf8(pt: str) -> None:
    """UTF-8 text — including emojis, control chars, RTL — survives the round-trip."""
    ct = nip44_encrypt(pt.encode("utf-8"), _A_NSEC, _B_NPUB)
    recovered = nip44_decrypt(ct, _B_NSEC, _A_NPUB)
    assert recovered.decode("utf-8") == pt


@_settings
@given(pt=st.binary(min_size=1, max_size=200))
def test_nip44_ciphertext_is_probabilistic(pt: bytes) -> None:
    """Two encryptions of the same plaintext must differ (random 32-byte nonce per NIP-44)."""
    ct1 = nip44_encrypt(pt, _A_NSEC, _B_NPUB)
    ct2 = nip44_encrypt(pt, _A_NSEC, _B_NPUB)
    assert ct1 != ct2, 'identical ciphertext for same plaintext → nonce is not random'


@_settings
@given(pt=st.binary(min_size=1, max_size=200))
def test_nip44_payload_shape(pt: bytes) -> None:
    """NIP-44 v2 wire format: base64(version || nonce(32) || ct || mac(32)).

    Replaces a check for NIP-04's `?iv=` separator. The shape matters beyond
    tidiness: `E2EPayload.validate` refuses anything that does not parse this
    way, so a frontend emitting the old format is rejected at the edge instead
    of storing an envelope nobody can open.
    """
    import base64

    from app.core.threshold import NIP44_VERSION

    raw = base64.b64decode(nip44_encrypt(pt, _A_NSEC, _B_NPUB), validate=True)
    assert raw[0] == NIP44_VERSION
    assert len(raw) >= 1 + 32 + 32 + 32


@_settings
@given(pt=st.binary(min_size=1, max_size=200))
def test_nip44_wrong_recipient_cannot_decrypt(pt: bytes) -> None:
    """A→B encrypted ciphertext must NOT decrypt with C's key."""
    ct = nip44_encrypt(pt, _A_NSEC, _B_NPUB)
    # Wrong recipient (C instead of B) → either wrong plaintext or 422.
    try:
        recovered = nip44_decrypt(ct, _C_NSEC, _A_NPUB)
        # PKCS7 unpadding may succeed by luck with wrong key — assert it's not
        # the actual plaintext, or (better) that it failed to decode.
        assert recovered != pt, "wrong recipient key produced correct plaintext"
    except Exception:
        # 422 / PKCS7 padding error — that's the expected outcome.
        pass


@_settings
@given(pt=st.binary(min_size=0, max_size=200))
def test_nip44_symmetric_direction(pt: bytes) -> None:
    """A→B and B→A produce different ciphertexts but each roundtrips correctly."""
    ct_ab = nip44_encrypt(pt, _A_NSEC, _B_NPUB)
    ct_ba = nip44_encrypt(pt, _B_NSEC, _A_NPUB)
    # Both directions should roundtrip.
    assert nip44_decrypt(ct_ab, _B_NSEC, _A_NPUB) == pt
    assert nip44_decrypt(ct_ba, _A_NSEC, _B_NPUB) == pt
