"""T_SEC.6 — the letter about a sign-in from somewhere the account has not been.

Two things are under test and they are not the same thing. One is the *rule* —
what counts as a new device, what the letter is allowed to say. The other is the
*plumbing* — that every door is wired, because a door nobody wired is exactly
where the hole would be.
"""
import uuid as uuidlib

import pytest

from tests.conftest import SEED_PASSWORD, make_account, unique_email

CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CHROME_NEWER = CHROME.replace("Chrome/120", "Chrome/131")
FIREFOX_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
)


@pytest.fixture
def device_letters(monkeypatch):
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(notif.send_new_device, "delay", lambda *a: sent.append(a))
    return sent


@pytest.fixture
def queued_codes(monkeypatch):
    from app.tasks import notifications as notif

    sent = []
    monkeypatch.setattr(notif.send_channel_code, "delay", lambda *a: sent.append(a))
    return sent


@pytest.fixture
def letters_sent(monkeypatch):
    """Records what actually reached `send_email`, for the tasks run directly."""
    from app.tasks import notifications as notif

    sent: list[tuple] = []

    def _send(to, subject, body, html=None):
        sent.append((to, subject, body, html))
        return True

    monkeypatch.setattr(notif, "send_email", _send)
    return sent


class _FakeRequest:
    def __init__(self, headers=None, host="198.51.100.7"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})()


# ── the trusted address ──────────────────────────────────────────────────────


def test_forwarded_for_is_read_from_the_right():
    """nginx appends its own view; everything left of it is the caller's text."""
    from app.core.client_ip import client_ip

    assert client_ip(_FakeRequest({"X-Forwarded-For": "1.2.3.4, 203.0.113.9"})) == (
        "203.0.113.9"
    )


def test_a_header_that_is_not_an_address_falls_through():
    """Here the request arrives with no proxy in front, so the header is
    entirely the caller's invention and the connection's own host is the truth.
    Parsing is what saves this case."""
    from app.core.client_ip import client_ip

    request = _FakeRequest({"X-Forwarded-For": "not-an-ip"}, host="198.51.100.7")
    assert client_ip(request) == "198.51.100.7"


def test_no_header_falls_back_to_the_peer():
    from app.core.client_ip import client_ip

    assert client_ip(_FakeRequest(host="192.0.2.5")) == "192.0.2.5"


def test_the_rate_limiter_keys_on_the_trusted_address():
    """The bug this fixes: every limit was one header away from not existing."""
    from app.core.rate_limit import _key_func

    assert _key_func(_FakeRequest({"X-Forwarded-For": "9.9.9.9, 203.0.113.9"})) == (
        "203.0.113.9"
    )


# ── what counts as a device ──────────────────────────────────────────────────


def test_a_browser_update_is_not_a_new_device():
    """Otherwise the letter arrives every time Chrome updates itself."""
    from app.core.sign_ins import describe, fingerprint, network_of

    network = network_of("203.0.113.9")
    assert fingerprint(describe(CHROME), network) == fingerprint(
        describe(CHROME_NEWER), network
    )


def test_a_different_browser_is_a_different_device():
    from app.core.sign_ins import describe, fingerprint, network_of

    network = network_of("203.0.113.9")
    assert fingerprint(describe(CHROME), network) != fingerprint(
        describe(FIREFOX_WINDOWS), network
    )


def test_moving_inside_the_same_network_is_not_a_new_device():
    from app.core.sign_ins import network_of

    assert network_of("203.0.113.9") == network_of("203.0.113.200")
    assert network_of("203.0.113.9") == "203.0.113.0/24"


def test_a_different_network_is_a_new_device():
    from app.core.sign_ins import network_of

    assert network_of("203.0.113.9") != network_of("198.51.100.9")


def test_ipv6_is_grouped_by_its_prefix():
    from app.core.sign_ins import network_of

    assert network_of("2001:db8:1:2::1") == network_of("2001:db8:1:ffff::9")


def test_an_unparseable_address_does_not_raise():
    from app.core.sign_ins import network_of

    assert network_of("nonsense") == "unknown"


def test_a_missing_user_agent_becomes_something_sayable():
    from app.core.sign_ins import describe

    assert describe(None) == "unknown device"
    assert describe("") == "unknown device"


def test_the_device_label_names_browser_and_system():
    from app.core.sign_ins import describe

    label = describe(CHROME)
    assert "Chrome" in label and "Mac" in label


# ── the doors ────────────────────────────────────────────────────────────────


async def _sign_in_with_password(
    client, email, *, agent=CHROME, forwarded="203.0.113.9"
):
    return await client.post(
        "/api/auth/login",
        json={"login": email, "password": SEED_PASSWORD},
        headers={"User-Agent": agent, "X-Forwarded-For": forwarded},
    )


async def _account(prefix: str):
    made = await make_account(
        {"email": unique_email(prefix), "password": SEED_PASSWORD, "display_name": "N"}
    )
    return made.json()["email"], made.json()["id"]


async def test_an_unknown_device_produces_a_letter(client, device_letters):
    email, _ = await _account("sec6-new")

    resp = await _sign_in_with_password(client, email)
    assert resp.status_code == 200
    assert len(device_letters) == 1
    assert "Chrome" in device_letters[0][1]


async def test_the_same_device_twice_produces_one_letter(client, device_letters):
    """Trap 1 of the task: a letter about every sign-in is one nobody reads."""
    email, _ = await _account("sec6-repeat")

    await _sign_in_with_password(client, email)
    await _sign_in_with_password(client, email)
    await _sign_in_with_password(client, email)
    assert len(device_letters) == 1


async def test_a_second_device_produces_a_second_letter(client, device_letters):
    email, _ = await _account("sec6-second")

    await _sign_in_with_password(client, email)
    await _sign_in_with_password(client, email, agent=FIREFOX_WINDOWS)
    assert len(device_letters) == 2


async def test_a_new_network_produces_a_letter(client, device_letters):
    email, _ = await _account("sec6-network")

    await _sign_in_with_password(client, email, forwarded="203.0.113.9")
    await _sign_in_with_password(client, email, forwarded="198.51.100.9")
    assert len(device_letters) == 2


async def test_a_spoofed_forwarded_for_does_not_choose_what_the_letter_says(
    client, device_letters
):
    """Acceptance: the attacker must not pick the address the owner reads.

    Both sign-ins claim a different left-hand value and share nginx's. One
    device, one letter — and the address handed to the letter is the trusted
    one, not either invention.
    """
    email, _ = await _account("sec6-spoof")

    await _sign_in_with_password(client, email, forwarded="8.8.8.8, 203.0.113.9")
    await _sign_in_with_password(client, email, forwarded="1.1.1.1, 203.0.113.9")

    assert len(device_letters) == 1
    assert device_letters[0][2] == "203.0.113.9"


async def test_signing_in_by_code_produces_a_letter(
    client, device_letters, queued_codes
):
    email, _ = await _account("sec6-code")

    await client.post(
        "/api/auth/otp/request",
        json={"identifier": email, "channel": "email", "locale": "en"},
    )
    code = queued_codes[-1][2]
    resp = await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": code},
        headers={"User-Agent": CHROME, "X-Forwarded-For": "203.0.113.9"},
    )
    assert resp.status_code == 200
    assert len(device_letters) == 1


async def test_creating_an_account_by_code_produces_no_letter(
    client, device_letters, queued_codes
):
    """A first device has nothing to be unlike."""
    email = unique_email("sec6-signup")

    await client.post(
        "/api/auth/otp/request",
        json={"identifier": email, "channel": "email", "locale": "en"},
    )
    code = queued_codes[-1][2]
    resp = await client.post(
        "/api/auth/otp/verify",
        json={"identifier": email, "code": code},
        headers={"User-Agent": CHROME, "X-Forwarded-For": "203.0.113.9"},
    )
    assert resp.status_code == 200
    assert device_letters == []


async def test_the_device_is_still_remembered_at_sign_up(
    client, device_letters, queued_codes
):
    """Silent, but not forgotten — otherwise the next sign-in raises a letter
    about the very machine the account was made on."""
    email = unique_email("sec6-remember")

    for _ in range(2):
        await client.post(
            "/api/auth/otp/request",
            json={"identifier": email, "channel": "email", "locale": "en"},
        )
        code = queued_codes[-1][2]
        await client.post(
            "/api/auth/otp/verify",
            json={"identifier": email, "code": code},
            headers={"User-Agent": CHROME, "X-Forwarded-For": "203.0.113.9"},
        )

    assert device_letters == []


async def test_a_recovery_code_records_the_device_without_a_second_letter(
    client, device_letters, monkeypatch, session_maker
):
    """One event, one letter. `send_recovery_code_used` is the one that fires."""
    from app.core.security import hash_recovery_code
    from app.models.user import RecoveryCode
    from app.tasks import notifications as notif

    recovery_letters = []
    monkeypatch.setattr(
        notif.send_recovery_code_used, "delay", lambda *a: recovery_letters.append(a)
    )

    email, user_id = await _account("sec6-recovery")
    async with session_maker() as db:
        db.add(
            RecoveryCode(
                user_id=uuidlib.UUID(user_id),
                code_hash=hash_recovery_code("ABCD-1234"),
            )
        )
        await db.commit()

    resp = await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": "ABCD-1234"},
        headers={"User-Agent": CHROME, "X-Forwarded-For": "203.0.113.9"},
    )
    assert resp.status_code == 200
    assert device_letters == [], "the recovery letter already says this"
    assert len(recovery_letters) == 1


async def test_the_device_from_a_recovery_is_remembered(
    client, device_letters, monkeypatch, session_maker
):
    """Otherwise the ordinary sign-in right after would raise a duplicate."""
    from app.core.security import hash_recovery_code
    from app.models.user import RecoveryCode
    from app.tasks import notifications as notif

    monkeypatch.setattr(notif.send_recovery_code_used, "delay", lambda *a: None)

    email, user_id = await _account("sec6-recovery-known")
    async with session_maker() as db:
        db.add(
            RecoveryCode(
                user_id=uuidlib.UUID(user_id),
                code_hash=hash_recovery_code("EFGH-5678"),
            )
        )
        await db.commit()

    await client.post(
        "/api/auth/recovery/consume",
        json={"identifier": email, "code": "EFGH-5678"},
        headers={"User-Agent": CHROME, "X-Forwarded-For": "203.0.113.9"},
    )
    await _sign_in_with_password(client, email)
    assert device_letters == []


async def test_a_failed_sign_in_teaches_us_nothing(
    client, device_letters, session_maker
):
    """A wrong password is not a sign-in, and must not register a device."""
    from sqlalchemy import func, select

    from app.models.sign_in import UserSignIn

    email, user_id = await _account("sec6-wrong")

    resp = await client.post(
        "/api/auth/login",
        json={"login": email, "password": "definitely-not-the-password"},
        headers={"User-Agent": CHROME, "X-Forwarded-For": "203.0.113.9"},
    )
    assert resp.status_code == 401
    assert device_letters == []

    async with session_maker() as db:
        rows = (
            await db.execute(
                select(func.count(UserSignIn.id)).where(
                    UserSignIn.user_id == uuidlib.UUID(user_id)
                )
            )
        ).scalar()
    assert rows == 0


# ── the letter itself ────────────────────────────────────────────────────────


def test_the_letter_exists_in_every_locale():
    """A key missing from one catalogue is a reader who gets English at the
    worst possible moment."""
    from app.core.email_templates import available_locales, render, sample_context

    for locale in available_locales():
        letter = render("new_device", locale, **sample_context("new_device"))
        assert letter.subject
        assert "Chrome on macOS" in letter.text
        assert "Chrome on macOS" in letter.html


def test_the_letter_survives_an_unknown_location():
    """The GeoLite2 file is optional; a missing place drops the line, not the
    letter."""
    from app.core.email_templates import render, sample_context

    letter = render("new_device", "en", **{**sample_context("new_device"), "place": ""})
    assert "Chrome on macOS" in letter.text
    assert "United Arab Emirates" not in letter.text


def test_the_letter_hedges_about_the_place():
    """Trap 2: geolocation lies, and the letter says so rather than accuses."""
    from app.core.email_templates import render, sample_context

    letter = render("new_device", "en", **sample_context("new_device"))
    assert "approximate" in letter.text.lower()


def test_geolocation_is_absent_without_a_database(monkeypatch):
    from app.core import geoip

    monkeypatch.setenv("GEOIP_DB_PATH", "")
    geoip._reader.cache_clear()
    assert geoip.place_for("203.0.113.9") is None
    geoip._reader.cache_clear()


class _FakeRecord:
    """Shaped like a `geoip2` City record, filled in only where a test cares.

    Built by hand rather than by shipping a cut-down `.mmdb`: the tiers below
    are branches in our code, and what is under test is which branch wins, not
    whether MaxMind can read its own file.
    """

    def __init__(self, city=None, region=None, country=None, zone=None):
        self.city = type("C", (), {"name": city})()
        self.country = type("C", (), {"name": country})()
        self.location = type("L", (), {"time_zone": zone})()
        self.subdivisions = type(
            "S", (), {"most_specific": type("M", (), {"name": region})()}
        )()


@pytest.fixture
def fake_geoip(monkeypatch):
    """Point `place_for` at a record the test wrote."""
    from app.core import geoip

    def _install(record):
        monkeypatch.setattr(
            geoip, "_reader", lambda: type("R", (), {"city": lambda self, ip: record})()
        )

    return _install


def test_a_city_wins_when_there_is_one(fake_geoip):
    from app.core.geoip import place_for

    fake_geoip(_FakeRecord(city="Minneapolis", country="United States"))
    assert place_for("128.101.101.101") == "Minneapolis, United States"


def test_the_region_stands_in_for_a_missing_city(fake_geoip):
    """Most real sign-ins have no city: VPNs, corporate egress, CGNAT."""
    from app.core.geoip import place_for

    fake_geoip(_FakeRecord(region="England", country="United Kingdom"))
    assert place_for("212.102.63.1") == "England, United Kingdom"


def test_the_time_zone_stands_in_for_a_missing_region(fake_geoip):
    """In a country nine zones wide, the zone is the difference between "that
    is my city" and "that is four thousand kilometres away"."""
    from app.core.geoip import place_for

    fake_geoip(_FakeRecord(country="Russia", zone="Europe/Moscow"))
    assert place_for("77.88.55.77") == "Russia (Europe/Moscow)"


def test_a_bare_country_is_still_better_than_nothing(fake_geoip):
    from app.core.geoip import place_for

    fake_geoip(_FakeRecord(country="United States"))
    assert place_for("8.8.8.8") == "United States"


def test_a_city_state_does_not_repeat_itself(fake_geoip):
    """"Singapore, Singapore" reads as a bug in the letter, not as a place."""
    from app.core.geoip import place_for

    fake_geoip(_FakeRecord(city="Singapore", country="Singapore"))
    assert place_for("203.0.113.9") == "Singapore"


def test_an_empty_record_yields_nothing(fake_geoip):
    """None, not a half-filled string: the letter drops the line entirely."""
    from app.core.geoip import place_for

    fake_geoip(_FakeRecord())
    assert place_for("203.0.113.9") is None


def test_a_lookup_that_raises_is_not_a_failed_letter(monkeypatch):
    from app.core import geoip

    class _Angry:
        def city(self, ip):
            raise RuntimeError("address not in database")

    monkeypatch.setattr(geoip, "_reader", lambda: _Angry())
    assert geoip.place_for("203.0.113.9") is None


def test_the_letter_ignores_the_notify_email_switch(sync_sessions, letters_sent):
    """Security letters are not a subscription — the class is unswitchable."""
    from app.models.user import User
    from app.tasks.notifications import send_new_device

    email = unique_email("sec6-unsubscribed")
    with sync_sessions() as db:
        user = User(email=email, display_name="Muted", locale="en", notify_email=False)
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = str(user.id)

    send_new_device(user_id, "Chrome on macOS", "203.0.113.9", "2026-08-11 09:00 UTC")
    assert any(call[0] == email for call in letters_sent)


def test_an_account_with_no_mailbox_is_not_an_error(sync_sessions, letters_sent):
    """A Nostr identity has nowhere to be told. Known limit, not a crash."""
    from app.models.user import User
    from app.tasks.notifications import send_new_device

    with sync_sessions() as db:
        user = User(email=None, display_name="Keyholder", locale="en")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = str(user.id)

    send_new_device(user_id, "Chrome on macOS", "203.0.113.9", "2026-08-11 09:00 UTC")
    assert letters_sent == []


# ── retention ────────────────────────────────────────────────────────────────


def test_old_sign_ins_are_forgotten(sync_sessions):
    """Ninety days is a rule; a rule nothing enforces is a sentence."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.sign_in import RETENTION_DAYS, UserSignIn
    from app.models.user import User
    from app.tasks.cleanup import purge_old_sign_ins

    now = datetime.now(timezone.utc)
    with sync_sessions() as db:
        user = User(email=unique_email("sec6-purge"), display_name="Old", locale="en")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        db.add(
            UserSignIn(
                user_id=user_id,
                fingerprint="a" * 64,
                device="Chrome on macOS",
                network="203.0.113.0/24",
                first_seen_at=now - timedelta(days=RETENTION_DAYS + 10),
                last_seen_at=now - timedelta(days=RETENTION_DAYS + 1),
            )
        )
        db.add(
            UserSignIn(
                user_id=user_id,
                fingerprint="b" * 64,
                device="Firefox on Windows",
                network="198.51.100.0/24",
                first_seen_at=now - timedelta(days=2),
                last_seen_at=now - timedelta(days=1),
            )
        )
        db.commit()

    purge_old_sign_ins()

    with sync_sessions() as db:
        remaining = (
            db.execute(select(UserSignIn).where(UserSignIn.user_id == user_id))
            .scalars()
            .all()
        )
    assert [row.fingerprint for row in remaining] == ["b" * 64]


def test_the_purge_task_is_registered():
    """A beat entry naming a task nobody registered is a job that never runs."""
    from app.worker import celery_app

    assert "app.tasks.cleanup.purge_old_sign_ins" in celery_app.tasks
    assert "purge-old-sign-ins-daily" in celery_app.conf.beat_schedule
