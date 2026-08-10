"""T3.1 — Уровень Бизнес-Активности (УБА) formula + endpoints."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.core.uba import LEVELS, UBAComponents, compute_uba, level_of
from tests.conftest import make_account


def _c(f=0, q=0, v=0.0, d=0.0, verify=None, verify_at=None) -> UBAComponents:
    # T_TRUST.1 — a fresh date by default. These cases are about the *level*
    # ladder, not about age; leaving the date empty would silently retest decay
    # everywhere and destroy what each assertion was written to prove. Decay has
    # its own tests below.
    return UBAComponents(
        f_count=f,
        q_count=q,
        v_sum=v,
        d_peak=d,
        verify_level=verify,
        verify_at=verify_at or datetime.now(timezone.utc),
    )


def test_zero_activity_yields_zero_uba():
    assert compute_uba(_c()) == 0


def test_max_saturation_hits_ceiling():
    """All components saturated → УБА ≈ 1000 (rounded)."""
    # F: 8 deals/month over 90 days = 24 closed deals; use 30 for margin.
    # Q: 50+ Q-eligible deals saturates log10 term.
    # V: $50k+ saturates.
    # D: $5k+ saturates → D_factor = 1.5.
    # Verify: kyc → V_verify_norm = 1.0.
    uba = compute_uba(_c(f=30, q=60, v=60000.0, d=6000.0, verify="kyc"))
    assert 990 <= uba <= 1000


def test_verify_factor_scales_score():
    """D=0 avoids the 1.5× D_factor pushing everything to the 1000 clamp so
    the four verify levels stay linearly separable."""
    base = compute_uba(_c(f=24, q=50, v=50000.0, d=0.0, verify=None))
    kyc = compute_uba(_c(f=24, q=50, v=50000.0, d=0.0, verify="kyc"))
    peer = compute_uba(_c(f=24, q=50, v=50000.0, d=0.0, verify="peer"))
    auto = compute_uba(_c(f=24, q=50, v=50000.0, d=0.0, verify="auto"))
    assert base < auto < peer < kyc
    # kyc is the ceiling — V_verify_norm = 1.0.
    assert kyc == round(base / (1.0 / 1.30))


def test_d_factor_is_multiplier_not_penalty():
    """No collateral → D_factor = 1.0 (neutral), not zero."""
    without_d = compute_uba(_c(f=6, q=10, v=1000.0, d=0.0, verify="peer"))
    with_max_d = compute_uba(_c(f=6, q=10, v=1000.0, d=10000.0, verify="peer"))
    # 1.5x boost from saturated D_factor.
    assert with_max_d == round(without_d * 1.5)
    # Baseline non-zero even without collateral.
    assert without_d > 0


def test_f_norm_uses_monthly_rate():
    """F is deals/month over 90-day window. 24 deals in 90 days = 8 deals/mo → saturated."""
    # 24 deals over 90 days → f_monthly = 24 / 3 = 8 → F_norm = 1.0 (saturated).
    # 12 deals → 4/mo → F_norm = 0.5.
    uba24 = compute_uba(_c(f=24, q=10, v=1000.0, d=0.0, verify=None))
    uba12 = compute_uba(_c(f=12, q=10, v=1000.0, d=0.0, verify=None))
    # Doubling F under saturation-safe conditions doubles the score
    # (Q/V/D/verify identical, F goes from 0.5 to 1.0).
    assert uba24 == round(uba12 * 2), (uba24, uba12)


def test_q_norm_logarithmic_shape():
    """log10(Q+1)/log10(51): Q=0 → 0, Q=50 → 1.0."""
    from app.core.uba import compute_uba as _c_uba

    zero_q = _c_uba(_c(f=24, q=0, v=50000.0, d=5000.0, verify="peer"))
    full_q = _c_uba(_c(f=24, q=50, v=50000.0, d=5000.0, verify="peer"))
    assert zero_q == 0  # Q=0 kills the product
    assert full_q > 0


def test_level_thresholds():
    assert level_of(0) == "newbie"
    assert level_of(49) == "newbie"
    assert level_of(50) == "verified"
    assert level_of(199) == "verified"
    assert level_of(200) == "reliable"
    assert level_of(449) == "reliable"
    assert level_of(450) == "trusted"
    assert level_of(749) == "trusted"
    assert level_of(750) == "elite"
    assert level_of(1000) == "elite"


def test_levels_ordered_and_slugs_stable():
    slugs = [s for _, s in LEVELS]
    assert slugs == ["newbie", "verified", "reliable", "trusted", "elite"]


async def test_uba_endpoint_returns_zero_for_fresh_user(client):
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("uba")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "Uba"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get("/api/me/uba", headers=hdr)
    assert resp.status_code == 200
    body = resp.json()
    assert body["uba"] == 0
    assert body["level"] == "newbie"
    assert body["components"]["f_count"] == 0
    assert body["components"]["q_count"] == 0
    assert body["components"]["v_sum"] == 0.0
    assert body["components"]["d_peak"] == 0.0


async def test_public_uba_endpoint_404_for_unknown_user(client, seed_sender):
    import uuid as _uuid
    from tests.conftest import SEED_PASSWORD, unique_email

    email = unique_email("ubaq")
    await make_account({"email": email, "password": SEED_PASSWORD, "display_name": "UbaQ"},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/users/{_uuid.uuid4()}/uba", headers=hdr)
    assert resp.status_code == 404


async def test_uba_scales_after_confirmed_deal(client, session_maker):
    """End-to-end: fresh carrier → 0 УБА → after a confirmed deal with photos,
    F/V move; Q stays 0 because we don't upload photos here → УБА stays 0
    (Q gates the product). This test proves the plumbing and the Q-gate."""
    from datetime import datetime, timedelta, timezone
    from tests.conftest import SEED_PASSWORD, unique_email

    c_email = unique_email("uba-c")
    await make_account({
            "email": c_email,
            "password": SEED_PASSWORD,
            "display_name": "UbaC",
            "can_carry": True,
            "active_mode": "carrier",
        },
    )
    c_login = await client.post(
        "/api/auth/login", json={"login": c_email, "password": SEED_PASSWORD}
    )
    c_headers = {"Authorization": f"Bearer {c_login.json()['access_token']}"}

    s_email = unique_email("uba-s")
    await make_account({"email": s_email, "password": SEED_PASSWORD, "display_name": "UbaS"},
    )
    s_login = await client.post(
        "/api/auth/login", json={"login": s_email, "password": SEED_PASSWORD}
    )
    s_headers = {"Authorization": f"Bearer {s_login.json()['access_token']}"}

    trip = await client.post(
        "/api/trips",
        headers=c_headers,
        json={
            "origin": "UBX",
            "destination": "UBY",
            "depart_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
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
                "recipient_contact": "+10000003333",
                "origin": "UBX",
                "destination": "UBY",
                "category": "document",
                "declared_value": 500.0,
            },
        },
    )
    deal_id = match.json()["id"]

    # Get carrier user id from /me.
    me = await client.get("/api/auth/me", headers=c_headers)
    carrier_id = me.json()["id"]

    # Confirm-close the deal.
    conf = await client.post(f"/api/deals/{deal_id}/confirm", headers=s_headers)
    assert conf.status_code == 200

    resp = await client.get(f"/api/users/{carrier_id}/uba", headers=c_headers)
    assert resp.status_code == 200
    body = resp.json()
    # F counts the closed deal; V has 500; but Q=0 because no photos → УБА=0.
    assert body["components"]["f_count"] == 1
    assert body["components"]["v_sum"] == 500.0
    assert body["components"]["q_count"] == 0
    assert body["uba"] == 0


# ── T_TRUST.1 — evidence decays ──────────────────────────────────────────────


def test_an_old_verification_is_worth_less_than_a_fresh_one():
    fresh = compute_uba(_c(f=24, q=50, v=50000.0, verify="kyc"))
    stale = compute_uba(
        _c(
            f=24,
            q=50,
            v=50000.0,
            verify="kyc",
            verify_at=datetime.now(timezone.utc) - timedelta(days=1825),
        )
    )
    assert stale < fresh


def test_decay_never_drops_below_having_no_verification_at_all():
    """The bonus decays toward 1.00, not toward zero.

    An ancient proof makes someone ordinary; it must never make them worse than
    a person who was never verified — that would turn evidence into a liability
    and give people a reason to avoid being verified at all.
    """
    unverified = compute_uba(_c(f=24, q=50, v=50000.0, verify=None))
    ancient = compute_uba(
        _c(
            f=24,
            q=50,
            v=50000.0,
            verify="kyc",
            verify_at=datetime.now(timezone.utc) - timedelta(days=36500),
        )
    )
    assert ancient >= unverified


def test_a_week_old_verification_is_still_full_strength():
    """Decay must not be felt immediately: "вчера" and "неделю назад" were
    called equally strong, and a score that visibly slips a day after a KYC
    would read as a bug to the person who just passed it."""
    now = datetime.now(timezone.utc)
    today = compute_uba(_c(f=24, q=50, v=50000.0, verify="kyc", verify_at=now))
    week = compute_uba(
        _c(f=24, q=50, v=50000.0, verify="kyc", verify_at=now - timedelta(days=7))
    )
    assert today == week


def test_unverified_accounts_are_untouched_by_decay():
    """No level means no bonus to decay — the factor stays exactly 1.00 and the
    date is irrelevant."""
    now = datetime.now(timezone.utc)
    recent = compute_uba(_c(f=24, q=50, v=50000.0, verify=None, verify_at=now))
    ancient = compute_uba(
        _c(f=24, q=50, v=50000.0, verify=None, verify_at=now - timedelta(days=9999))
    )
    assert recent == ancient
