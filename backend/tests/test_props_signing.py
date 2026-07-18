"""T_TEST.5 — property-based invariants for NIP-01 signing (T2.2 pt.2).

Roundtrip: `compute_event_id → sign_event_id → verify_event_id` must succeed
for any well-formed event. Tampering with any field must break verification.
"""
from __future__ import annotations

from hypothesis import assume, given, settings, strategies as st

from app.core.keypair import generate_keypair, sign_event_id, verify_event_id
from app.core.signing import compute_event_id

_NSEC, _NPUB = generate_keypair()
_OTHER_NSEC, _OTHER_NPUB = generate_keypair()

_settings = settings(max_examples=100, deadline=None)


# Strategies for legal event components.
_kind_strat = st.integers(min_value=0, max_value=65_535)
_ts_strat = st.integers(min_value=0, max_value=2**31 - 1)
_content_strat = st.text(min_size=0, max_size=300)
_tag_strat = st.lists(
    st.lists(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
        ),
        min_size=1,
        max_size=4,
    ),
    max_size=6,
)


@_settings
@given(_kind_strat, _ts_strat, _content_strat, _tag_strat)
def test_sign_verify_roundtrip(kind, ts, content, tags):
    """Any well-formed event: sign then verify with the same key succeeds."""
    event_id = compute_event_id(_NPUB, ts, kind, tags, content)
    sig = sign_event_id(event_id, _NSEC)
    assert verify_event_id(event_id, sig, _NPUB)


@_settings
@given(_kind_strat, _ts_strat, _content_strat, _tag_strat)
def test_event_id_deterministic(kind, ts, content, tags):
    """Same inputs → same 32-byte hex event id (pure function)."""
    id1 = compute_event_id(_NPUB, ts, kind, tags, content)
    id2 = compute_event_id(_NPUB, ts, kind, tags, content)
    assert id1 == id2
    assert len(id1) == 64  # 32 bytes hex


@_settings
@given(_kind_strat, _ts_strat, _content_strat, _content_strat)
def test_content_change_breaks_verification(kind, ts, c1, c2):
    """Signing id(c1) then verifying id(c2) must fail — content is bound to sig."""
    assume(c1 != c2)
    id1 = compute_event_id(_NPUB, ts, kind, [], c1)
    id2 = compute_event_id(_NPUB, ts, kind, [], c2)
    assume(id1 != id2)
    sig = sign_event_id(id1, _NSEC)
    assert not verify_event_id(id2, sig, _NPUB)


@_settings
@given(_kind_strat, _ts_strat, _content_strat, _tag_strat)
def test_wrong_pubkey_fails(kind, ts, content, tags):
    """Signature made with key A never verifies against pubkey B."""
    event_id = compute_event_id(_NPUB, ts, kind, tags, content)
    sig = sign_event_id(event_id, _NSEC)
    assert not verify_event_id(event_id, sig, _OTHER_NPUB)


@_settings
@given(_kind_strat, _ts_strat, _content_strat, _tag_strat, _ts_strat)
def test_timestamp_change_breaks_id(kind, ts1, content, tags, ts2):
    """Timestamps are part of the id — different ts → different id."""
    assume(ts1 != ts2)
    id1 = compute_event_id(_NPUB, ts1, kind, tags, content)
    id2 = compute_event_id(_NPUB, ts2, kind, tags, content)
    assert id1 != id2


@_settings
@given(_kind_strat, _kind_strat, _ts_strat, _content_strat, _tag_strat)
def test_kind_change_breaks_id(k1, k2, ts, content, tags):
    """Different kinds → different ids."""
    assume(k1 != k2)
    id1 = compute_event_id(_NPUB, ts, k1, tags, content)
    id2 = compute_event_id(_NPUB, ts, k2, tags, content)
    assert id1 != id2
