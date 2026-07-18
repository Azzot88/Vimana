"""T_TEST.5 — property-based invariants for UBA formula (T3.1).

Formula: `УБА = round(F_norm × Q_norm × V_norm × D_factor × V_verify_norm × 1000)`
clamped to [0, 1000]. Property tests prove the invariants hold for any input,
not just the hand-picked cases in `test_uba.py`.
"""
from __future__ import annotations

from hypothesis import assume, given, settings, strategies as st

from app.core.uba import LEVELS, UBAComponents, compute_uba, level_of

_settings = settings(max_examples=200, deadline=None)


def _c(**kw) -> UBAComponents:
    return UBAComponents(
        f_count=kw.get("f", 0),
        q_count=kw.get("q", 0),
        v_sum=kw.get("v", 0.0),
        d_peak=kw.get("d", 0.0),
        verify_level=kw.get("verify"),
    )


# Reusable strategies.
_f_strat = st.integers(min_value=0, max_value=10_000)
_q_strat = st.integers(min_value=0, max_value=10_000)
_v_strat = st.floats(
    min_value=0.0, max_value=10_000_000.0, allow_nan=False, allow_infinity=False
)
_d_strat = st.floats(
    min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
)
_verify_strat = st.sampled_from([None, "auto", "peer", "kyc"])


@_settings
@given(_f_strat, _q_strat, _v_strat, _d_strat, _verify_strat)
def test_uba_always_in_range(f, q, v, d, verify):
    """UBA must never leave [0, 1000] regardless of inputs (clamp guarantee)."""
    u = compute_uba(_c(f=f, q=q, v=v, d=d, verify=verify))
    assert 0 <= u <= 1000


@_settings
@given(_f_strat, _f_strat, _q_strat, _v_strat, _d_strat, _verify_strat)
def test_uba_monotonic_in_f(f1, f2, q, v, d, verify):
    """More closed deals as carrier can only raise UBA (never lower)."""
    assume(f1 <= f2)
    u1 = compute_uba(_c(f=f1, q=q, v=v, d=d, verify=verify))
    u2 = compute_uba(_c(f=f2, q=q, v=v, d=d, verify=verify))
    assert u1 <= u2


@_settings
@given(_f_strat, _q_strat, _q_strat, _v_strat, _d_strat, _verify_strat)
def test_uba_monotonic_in_q(f, q1, q2, v, d, verify):
    """More Q-eligible deals can only raise UBA."""
    assume(q1 <= q2)
    u1 = compute_uba(_c(f=f, q=q1, v=v, d=d, verify=verify))
    u2 = compute_uba(_c(f=f, q=q2, v=v, d=d, verify=verify))
    assert u1 <= u2


@_settings
@given(_f_strat, _q_strat, _v_strat, _v_strat, _d_strat, _verify_strat)
def test_uba_monotonic_in_v(f, q, v1, v2, d, verify):
    """Larger declared_value can only raise UBA."""
    assume(v1 <= v2)
    u1 = compute_uba(_c(f=f, q=q, v=v1, d=d, verify=verify))
    u2 = compute_uba(_c(f=f, q=q, v=v2, d=d, verify=verify))
    assert u1 <= u2


@_settings
@given(_f_strat, _q_strat, _v_strat, _d_strat, _d_strat, _verify_strat)
def test_uba_monotonic_in_d(f, q, v, d1, d2, verify):
    """More collateral can only raise UBA (D_factor is 1+, never penalty)."""
    assume(d1 <= d2)
    u1 = compute_uba(_c(f=f, q=q, v=v, d=d1, verify=verify))
    u2 = compute_uba(_c(f=f, q=q, v=v, d=d2, verify=verify))
    assert u1 <= u2


@_settings
@given(_f_strat, _q_strat, _v_strat, _d_strat)
def test_uba_verify_hierarchy(f, q, v, d):
    """None ≤ auto ≤ peer ≤ kyc — verification always non-decreasing.

    Skip degenerate case where all components are 0 (product is 0, all levels
    equal, no useful hierarchy assertion)."""
    assume(f > 0 and q > 0 and v > 0)
    u_none = compute_uba(_c(f=f, q=q, v=v, d=d, verify=None))
    u_auto = compute_uba(_c(f=f, q=q, v=v, d=d, verify="auto"))
    u_peer = compute_uba(_c(f=f, q=q, v=v, d=d, verify="peer"))
    u_kyc = compute_uba(_c(f=f, q=q, v=v, d=d, verify="kyc"))
    assert u_none <= u_auto <= u_peer <= u_kyc


@_settings
@given(_f_strat, _q_strat, _v_strat, _d_strat, _verify_strat)
def test_uba_deterministic(f, q, v, d, verify):
    """Same input → same output (pure function invariant)."""
    c = _c(f=f, q=q, v=v, d=d, verify=verify)
    assert compute_uba(c) == compute_uba(c)


@_settings
@given(st.integers(min_value=0, max_value=1000))
def test_level_returns_valid_slug(u):
    """level_of never returns an out-of-vocab slug."""
    valid = {name for _, name in LEVELS}
    assert level_of(u) in valid


@_settings
@given(_f_strat, _v_strat, _d_strat, _verify_strat)
def test_zero_q_yields_zero_uba(f, v, d, verify):
    """Q=0 means log10(1)/log10(51)=0, product=0, so UBA=0 regardless of others."""
    u = compute_uba(_c(f=f, q=0, v=v, d=d, verify=verify))
    assert u == 0


@_settings
@given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=1000))
def test_level_of_monotonic(u1, u2):
    """u1 ≤ u2 → tier(u1) is ≤ tier(u2) in ordering (never a downgrade)."""
    assume(u1 <= u2)
    order = [name for _, name in LEVELS]
    idx1 = order.index(level_of(u1))
    idx2 = order.index(level_of(u2))
    assert idx1 <= idx2
