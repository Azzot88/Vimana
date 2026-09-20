"""T_SEC.7 — сутки на доказательство личности.

Owner, 2026-09-20: «24h+ → reauth · 30 days inactive → logout · critical
operation → reauth immediately». This file covers the first rule and the clock
that extends it; the idle limit is the client's timer, and the critical
operations are `test_step_up.py`.

The shape of the rule: a session is a token, the moment identity was proved is
its `iat`, and after a day that proof stops opening doors — but the account is
still the account, so the screen must be able to say whose it is and let them
prove it again by any means they have.
"""
from __future__ import annotations

import jwt

from app.core.config import settings
from app.core.security import create_access_token


def _aged(token: str, seconds: int) -> str:
    """The same session, minted `seconds` ago.

    Re-signed rather than slept for: the rule is about a timestamp, and a test
    that waits a day is a test nobody runs.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    payload["iat"] = payload["iat"] - seconds
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def test_a_session_within_the_day_works(client, seed_sender):
    fresh = create_access_token(str(seed_sender.id))
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"})
    assert r.status_code == 200, r.text


async def test_a_day_old_session_is_refused_with_its_own_reason(client, seed_sender):
    """Not a bare 401: «докажи, что это ты» and «этот токен не твой» lead to
    different screens, and the client has to tell them apart."""
    stale = _aged(create_access_token(str(seed_sender.id)), 25 * 3600)

    # `/api/deals` rather than the trip listing: that one is a page a stranger
    # may read, so it takes the optional dependency and answers a session it
    # cannot vouch for as it answers anybody with no session at all — publicly,
    # and with nothing of the account in it. This door is the account's own.
    r = await client.get("/api/deals", headers={"Authorization": f"Bearer {stale}"})
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "reauth_required"


async def test_the_stale_session_still_says_whose_it_is(client, seed_sender):
    """`/auth/me` is the one door left open: the dialog asking somebody to
    prove themselves has to name the account it is asking about."""
    stale = _aged(create_access_token(str(seed_sender.id)), 25 * 3600)

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(seed_sender.id)


async def test_signing_in_again_restores_the_day(client, seed_sender):
    from tests.conftest import SEED_PASSWORD

    login = await client.post(
        "/api/auth/login",
        json={"login": seed_sender.email, "password": SEED_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    # The same account-only door the stale session was refused at, so this
    # answers «the sign-in restored it» and not «that page is public anyway».
    r = await client.get("/api/deals", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


async def test_confirming_an_operation_starts_the_day_over(client, seed_sender):
    """Owner, 2026-09-20: the clock is pushed forward by **any** proof, and a
    step-up is one. Confirming something at hour 23 must not leave the person
    thrown out an hour later."""
    from tests.conftest import SEED_PASSWORD

    login = await client.post(
        "/api/auth/login",
        json={"login": seed_sender.email, "password": SEED_PASSWORD},
    )
    token = login.json()["access_token"]

    verified = await client.post(
        "/api/auth/step-up/verify",
        headers={"Authorization": f"Bearer {token}"},
        json={"scope": "change_password", "password": SEED_PASSWORD},
    )
    assert verified.status_code == 200, verified.text
    replacement = verified.json()["access_token"]
    assert replacement and replacement != token

    # The new one is a working session, and it is the one the client keeps.
    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {replacement}"}
    )
    assert r.status_code == 200, r.text
