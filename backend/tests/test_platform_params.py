"""T3.40 — business-logic parameters: resolution, versioning, access.

The interesting cases are not "does the form save". They are: does an empty
table still yield a working platform, does a corridor row shadow the global one,
does history survive a change, and can a non-superuser reach the screen by
calling the API directly.
"""
from __future__ import annotations

import pytest
from tests.conftest import SEED_PASSWORD, make_account, unique_email



async def _superuser_headers(client, session_maker) -> dict[str, str]:
    from sqlalchemy import select

    from app.models.user import User

    email = unique_email("params-adm")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Params Adm"}
    )
    async with session_maker() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        u.role = "superuser"
        await db.commit()
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _plain_headers(client) -> dict[str, str]:
    email = unique_email("params-usr")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "Params Usr"}
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# ── access ────────────────────────────────────────────────────────────────


async def test_list_requires_permission(client):
    """Hiding the menu entry is not the control; the endpoint is."""
    hdr = await _plain_headers(client)
    r = await client.get("/api/admin/params", headers=hdr)
    assert r.status_code == 403, r.text


async def test_set_requires_permission(client):
    hdr = await _plain_headers(client)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "carrier_fee_percent", "value": "99"},
    )
    assert r.status_code == 403, r.text


async def test_list_unauthenticated_rejected(client):
    r = await client.get("/api/admin/params")
    assert r.status_code in (401, 403)


# ── defaults ──────────────────────────────────────────────────────────────


async def test_empty_table_yields_working_defaults(client, session_maker):
    """A platform with no rows runs on MASTERPLAN §4.1, not on nulls."""
    hdr = await _superuser_headers(client, session_maker)
    r = await client.get("/api/admin/params", headers=hdr)
    assert r.status_code == 200, r.text
    rows = {p["key"]: p for p in r.json()}

    assert "carrier_fee_percent" in rows
    assert "b2b_platform_share_percent" in rows
    # Whatever else is true, the platform must never report a rate of nothing.
    assert all(p["value"] not in (None, "") for p in rows.values())


async def test_untouched_parameter_is_labelled_default(client, session_maker):
    """The screen has to distinguish a number somebody chose from one nobody
    did — otherwise a placeholder reads as a decision."""
    hdr = await _superuser_headers(client, session_maker)
    r = await client.get("/api/admin/params", headers=hdr)
    row = next(p for p in r.json() if p["key"] == "volumetric_divisor")
    if row["source"] == "default":
        assert row["effective_from"] is None


# ── writing ───────────────────────────────────────────────────────────────


async def test_set_then_read_back(client, session_maker):
    hdr = await _superuser_headers(client, session_maker)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={
            "key": "carrier_fee_percent",
            "value": "4",
            "comment": "проба",
        },
    )
    assert r.status_code == 201, r.text

    listing = await client.get("/api/admin/params", headers=hdr)
    row = next(p for p in listing.json() if p["key"] == "carrier_fee_percent")
    assert row["value"] == "4"
    assert row["source"] == "global"
    assert row["comment"] == "проба"


async def test_change_appends_version_and_keeps_history(client, session_maker):
    """A change must never edit a row: "what was the fee that day" has to stay
    answerable from the table."""
    hdr = await _superuser_headers(client, session_maker)
    for value in ("5", "6"):
        r = await client.post(
            "/api/admin/params",
            headers=hdr,
            json={"key": "escrow_tier1_percent", "value": value},
        )
        assert r.status_code == 201, r.text

    hist = await client.get(
        "/api/admin/params/escrow_tier1_percent/history", headers=hdr
    )
    assert hist.status_code == 200
    values = [h["value"] for h in hist.json()]
    assert "5" in values and "6" in values
    # Newest first — the screen shows the current value at the top.
    assert values[0] == "6"


async def test_author_is_recorded(client, session_maker):
    """Audit without an author is a log, not an audit."""
    hdr = await _superuser_headers(client, session_maker)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "premium_price_month", "value": "12"},
    )
    assert r.status_code == 201
    assert r.json()["created_by_id"] is not None


# ── scope ─────────────────────────────────────────────────────────────────


async def test_corridor_shadows_global(client, session_maker):
    """The minimum bond on UAE→US and on an intra-EU route cannot be one
    number — that is the whole reason scope exists."""
    hdr = await _superuser_headers(client, session_maker)
    await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "min_bond_tier1", "value": "100"},
    )
    await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "min_bond_tier1", "value": "900", "scope": "AE->US"},
    )

    glob = await client.get("/api/admin/params", headers=hdr)
    grow = next(p for p in glob.json() if p["key"] == "min_bond_tier1")
    assert grow["value"] == "100"
    assert grow["source"] == "global"

    corr = await client.get(
        "/api/admin/params", headers=hdr, params={"scope": "AE->US"}
    )
    crow = next(p for p in corr.json() if p["key"] == "min_bond_tier1")
    assert crow["value"] == "900"
    assert crow["source"] == "corridor"


async def test_corridor_without_own_row_falls_back_to_global(client, session_maker):
    hdr = await _superuser_headers(client, session_maker)
    await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "shop_pool_min_bond", "value": "250"},
    )
    corr = await client.get(
        "/api/admin/params", headers=hdr, params={"scope": "PL->GB"}
    )
    row = next(p for p in corr.json() if p["key"] == "shop_pool_min_bond")
    assert row["value"] == "250"
    assert row["source"] == "global"


async def test_malformed_scope_rejected(client, session_maker):
    hdr = await _superuser_headers(client, session_maker)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "min_bond_tier1", "value": "1", "scope": "AE_US"},
    )
    assert r.status_code == 422, r.text


# ── validation ────────────────────────────────────────────────────────────


async def test_unknown_key_rejected(client, session_maker):
    hdr = await _superuser_headers(client, session_maker)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "not_a_parameter", "value": "1"},
    )
    assert r.status_code == 404, r.text


async def test_non_numeric_value_rejected_at_write(client, session_maker):
    """Catch it at the form, not at settlement — a bad rate discovered while
    closing a deal surfaces as a broken deal."""
    hdr = await _superuser_headers(client, session_maker)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "carrier_fee_percent", "value": "три процента"},
    )
    assert r.status_code == 422, r.text


async def test_empty_value_rejected(client, session_maker):
    hdr = await _superuser_headers(client, session_maker)
    r = await client.post(
        "/api/admin/params",
        headers=hdr,
        json={"key": "carrier_fee_percent", "value": "   "},
    )
    assert r.status_code == 422, r.text


async def test_history_of_unknown_key_is_404(client, session_maker):
    hdr = await _superuser_headers(client, session_maker)
    r = await client.get("/api/admin/params/nope/history", headers=hdr)
    assert r.status_code == 404


# ── the resolver itself ───────────────────────────────────────────────────


async def test_future_effective_from_does_not_apply_yet(client, session_maker):
    """Scheduling a change must not change anything today — the same property
    that keeps a rate change from reaching backwards into a shipment."""
    from datetime import datetime, timedelta, timezone

    hdr = await _superuser_headers(client, session_maker)
    later = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    await client.post(
        "/api/admin/params",
        headers=hdr,
        json={
            "key": "b2b_price_per_kg",
            "value": "99",
            "effective_from": later,
        },
    )
    listing = await client.get("/api/admin/params", headers=hdr)
    row = next(p for p in listing.json() if p["key"] == "b2b_price_per_kg")
    assert row["value"] != "99"


async def test_resolve_at_past_moment_sees_past_value(session_maker):
    """`resolve(at=...)` is what a deal will use to read the rate it was struck
    under rather than the rate in force now."""
    from datetime import datetime, timedelta, timezone

    from app.core.params import resolve
    from app.models.platform_params import ParamValueType, PlatformParameter

    now = datetime.now(timezone.utc)
    async with session_maker() as db:
        db.add(
            PlatformParameter(
                key="escrow_tier3_percent",
                scope="global",
                value="7",
                value_type=ParamValueType.percent,
                effective_from=now - timedelta(days=10),
            )
        )
        db.add(
            PlatformParameter(
                key="escrow_tier3_percent",
                scope="global",
                value="8",
                value_type=ParamValueType.percent,
                effective_from=now - timedelta(days=1),
            )
        )
        await db.commit()

        recent = await resolve(db, "escrow_tier3_percent")
        earlier = await resolve(
            db, "escrow_tier3_percent", at=now - timedelta(days=5)
        )

    assert str(recent) == "8"
    assert str(earlier) == "7"


async def test_resolve_unknown_key_raises(session_maker):
    from app.core.params import resolve

    async with session_maker() as db:
        with pytest.raises(KeyError):
            await resolve(db, "no_such_parameter")
