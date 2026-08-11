"""T3.29 — how much of the code form one caller gets to use.

The limits that already existed count *requests*: slowapi per endpoint, nginx
per address, and a sixty-second cooldown per value. None of them counted the
thing that matters — how many different people's mailboxes one caller writes to.

**Most of these go through `/password/forgot` rather than `/otp/request`.** Not
for convenience: `contact_verification` refuses a second code for the same value
inside sixty seconds, so a test that asked for six in a row would be measuring
that cooldown and not this budget. The reset form has no cooldown and puts mail
in the same box, which makes it the honest instrument here — and the last test
below is the one that proves the two forms share one budget.

These tests switch `RATE_LIMIT_ENABLED` back on deliberately. The suite runs
with it off so fixtures can ask for dozens of codes; a module testing the
limiter with the limiter disabled would be the exact failure `T_TEST.7` records,
where five tests passed for a month because the feature was off underneath them.
"""
import secrets

import pytest

from tests.conftest import unique_email

# Counters live in Redis for an hour, which outlives the suite. Fixed addresses
# would mean the second run of the day inheriting the first run's spent budget
# and failing for a reason that has nothing to do with the code — so each run
# gets its own block of source addresses.
_RUN = f"10.{secrets.randbelow(250)}.{secrets.randbelow(250)}"


@pytest.fixture(autouse=True)
def limits_on(monkeypatch):
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit, "RATE_LIMIT_ENABLED", True)


@pytest.fixture(autouse=True)
def queued_codes(monkeypatch):
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: sent.append(a))
    monkeypatch.setattr(notif.send_password_reset, "delay", lambda *a: None)
    return sent


def _ip(suffix: int) -> str:
    """A source address unique to this run and this test."""
    return f"{_RUN}.{suffix}"


async def _forgot(client, identifier, ip):
    return await client.post(
        "/api/auth/password/forgot",
        json={"identifier": identifier},
        headers={"X-Forwarded-For": ip},
    )


async def _code(client, identifier, ip):
    return await client.post(
        "/api/auth/otp/request",
        json={"identifier": identifier, "channel": "email", "locale": "en"},
        headers={"X-Forwarded-For": ip},
    )


async def test_a_person_who_mistypes_notices_nothing(client):
    """The limit exists for the mailer, not for the human who fumbled an
    address and typed it again correctly."""
    ip = _ip(11)
    assert (await _code(client, unique_email("limit-typo"), ip)).status_code == 202
    assert (await _code(client, unique_email("limit-fixed"), ip)).status_code == 202


async def test_one_mailbox_cannot_be_buried(client):
    """Above the budget the same address stops receiving, however the requests
    are spread — a different source each time, so this cannot be the per-source
    counter passing the test for the wrong reason."""
    from app.core.code_limits import PER_IDENTIFIER

    email = unique_email("limit-value")
    for index in range(PER_IDENTIFIER):
        resp = await _forgot(client, email, _ip(20 + index))
        assert resp.status_code == 202, f"request {index} should still pass"

    assert (await _forgot(client, email, _ip(29))).status_code == 429


async def test_one_source_cannot_write_to_the_whole_world(client):
    """Ten mailboxes an hour is generous for a person and useless for a mailer."""
    from app.core.code_limits import IDENTIFIERS_PER_IP

    ip = _ip(31)
    for index in range(IDENTIFIERS_PER_IP):
        resp = await _code(client, unique_email(f"limit-spread-{index}"), ip)
        assert resp.status_code == 202, f"mailbox {index} should still pass"

    assert (await _code(client, unique_email("limit-last"), ip)).status_code == 429


async def test_retrying_your_own_address_is_not_a_new_mailbox(client):
    """Otherwise a caller behind a full source is refused for the behaviour of
    somebody else on the same carrier."""
    from app.core.code_limits import IDENTIFIERS_PER_IP

    ip = _ip(41)
    mine = unique_email("limit-mine")
    assert (await _forgot(client, mine, ip)).status_code == 202

    for index in range(IDENTIFIERS_PER_IP + 5):
        await _forgot(client, unique_email(f"limit-filler-{index}"), ip)

    # The source's budget is long gone, but this address is already in the set.
    assert (await _forgot(client, mine, ip)).status_code == 202


async def test_the_two_forms_share_one_budget(client):
    """A caller cannot get a second allowance by switching endpoints: both put
    mail in the same box."""
    from app.core.code_limits import PER_IDENTIFIER

    ip = _ip(51)
    email = unique_email("limit-shared")
    for _ in range(PER_IDENTIFIER):
        assert (await _forgot(client, email, ip)).status_code == 202

    assert (await _code(client, email, ip)).status_code == 429


async def test_a_redis_outage_does_not_close_the_door(client, monkeypatch):
    """The same trade the rate limiter makes on purpose: ordinary traffic
    prefers availability, and nginx's zones still stand in front. A limiter
    whose own storage failing locks the front door is worse than the abuse it
    prevents."""
    from app.core import code_limits

    def _explode():
        raise RuntimeError("redis is gone")

    monkeypatch.setattr("app.core.redis_client.get_client", _explode)

    email = unique_email("limit-outage")
    for _ in range(code_limits.PER_IDENTIFIER + 3):
        assert (await _forgot(client, email, _ip(61))).status_code == 202


async def test_the_check_is_skipped_when_limits_are_off(client, monkeypatch):
    """The other half of the switch the rest of the suite depends on."""
    from app.core import code_limits, rate_limit

    monkeypatch.setattr(rate_limit, "RATE_LIMIT_ENABLED", False)

    email = unique_email("limit-disabled")
    for _ in range(code_limits.PER_IDENTIFIER + 3):
        assert (await _forgot(client, email, _ip(71))).status_code == 202
