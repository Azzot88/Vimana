"""T3.32 — event class × channel.

The thing under test is a decision, not a table: given an account, a class of
event and a channel, does the message go. Everything else here — the stored
shape, the API, the merge — exists to build that decision, and is tested for the
ways it could quietly give the wrong one.
"""
import pytest

from tests.conftest import SEED_PASSWORD, make_account, unique_email


@pytest.fixture
def spy(monkeypatch):
    """Record what each transport was handed, without sending anything."""
    from app.tasks import notifications as notif

    sent = {"email": [], "telegram": [], "whatsapp": []}
    monkeypatch.setattr(
        notif, "send_email", lambda to, s, b, h=None: sent["email"].append(to) or True
    )
    monkeypatch.setattr(
        notif, "send_telegram", lambda chat, text: sent["telegram"].append(chat)
    )
    monkeypatch.setattr(
        notif, "send_whatsapp", lambda number, text: sent["whatsapp"].append(number)
    )
    return sent


def _user(maker, **fields):
    from app.models.user import User

    # Defaults, not hardcoded values: a test that wants an account *without* a
    # chat has to be able to say so, and passing the same keyword twice is a
    # `TypeError` rather than an override.
    fields.setdefault("telegram_chat_id", "chat-123")

    with maker() as db:
        user = User(
            email=unique_email("prefs"),
            display_name="Matrix Tester",
            locale="en",
            **fields,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


# ── the decision ─────────────────────────────────────────────────────────────


def test_an_untouched_account_gets_everything(sync_sessions, spy):
    """A gap in the stored blob is the default, and the default is «send»."""
    from app.tasks.notifications import _notify_user

    user = _user(sync_sessions)
    _notify_user(user, "deal_status", status="delivered")

    assert len(spy["email"]) == 1
    assert len(spy["telegram"]) == 1


def test_one_class_can_be_quietened_on_one_channel(sync_sessions, spy):
    """The whole point: deals in Telegram, deadlines only by mail."""
    from app.tasks.notifications import _notify_user

    user = _user(
        sync_sessions,
        notification_prefs={"deadline": {"telegram": False}},
    )

    _notify_user(user, "deal_status", status="delivered")
    _notify_user(user, "deadline_reminder")

    assert len(spy["email"]) == 2, "mail was never switched off"
    assert len(spy["telegram"]) == 1, "only the deal reached Telegram"


def test_a_switched_off_class_is_not_delivered(sync_sessions, spy):
    from app.tasks.notifications import _notify_user

    user = _user(
        sync_sessions,
        notification_prefs={"deal": {"email": False, "telegram": False}},
    )
    _notify_user(user, "deal_status", status="delivered")

    assert spy["email"] == []
    assert spy["telegram"] == []


def test_security_is_delivered_with_everything_switched_off(sync_sessions, spy):
    """Since T3.28 a mailbox alone opens the account. A signal you can turn off
    is not a signal — it is a setting."""
    from app.tasks.notifications import _notify_user

    user = _user(
        sync_sessions,
        notification_prefs={
            "deal": {"email": False, "telegram": False},
            "security": {"email": False, "telegram": False},
        },
    )
    _notify_user(user, "new_device", device="Chrome on macOS", place="", when="now")

    assert len(spy["email"]) == 1
    assert len(spy["telegram"]) == 1


def test_an_unknown_key_reads_as_the_default(sync_sessions, spy):
    """A blob written by a newer deploy must not silence an older one."""
    from app.tasks.notifications import _notify_user

    user = _user(
        sync_sessions,
        notification_prefs={"invented_class": {"email": False}, "deal": {}},
    )
    _notify_user(user, "deal_status", status="delivered")

    assert len(spy["email"]) == 1


def test_a_preference_without_an_address_delivers_nothing(sync_sessions, spy):
    """Wanting Telegram is not the same as having a chat to send to."""
    from app.tasks.notifications import _notify_user

    user = _user(sync_sessions, telegram_chat_id=None)
    _notify_user(user, "deal_status", status="delivered")

    assert len(spy["email"]) == 1
    assert spy["telegram"] == []


def test_an_unclassified_letter_is_delivered_rather_than_dropped(sync_sessions, spy):
    """A message with no class is a bug. Swallowing it is the worse of the two
    outcomes: nobody ever learns the thing happened."""
    from app.tasks.notifications import _notify_user

    user = _user(sync_sessions, notification_prefs={"deal": {"email": False}})
    _notify_user(user, "waitlist_confirmation")

    assert len(spy["email"]) == 1


# ── the registry ─────────────────────────────────────────────────────────────


def test_every_class_kind_is_a_real_letter():
    """A class pointing at a template that does not exist would fail at send
    time, in a Celery worker, for one user."""
    from app.core.email_templates import _LETTERS
    from app.core.notification_prefs import EVENT_CLASSES

    for cls in EVENT_CLASSES:
        for kind in cls.kinds:
            assert kind in _LETTERS, f"{cls.key} claims unknown letter {kind}"


def test_classes_with_nothing_to_send_are_not_shown():
    """A switch for a message that never arrives is a promise the product does
    not keep."""
    from app.core.notification_prefs import visible_classes

    shown = {cls.key for cls in visible_classes()}
    assert shown == {"deal", "deadline", "security"}


def test_security_is_the_locked_class():
    from app.core.notification_prefs import locked_classes

    assert locked_classes() == ["security"]


def test_all_three_channels_are_columns(monkeypatch):
    """Owner's decision 2026-08-11. The earlier rule hid a channel until
    `channels.enabled` said yes, which left a person unable to tell whether
    WhatsApp exists here at all. It is shown, and `connected_channels` is what
    makes it read as unusable."""
    from app.core.notification_prefs import active_channels

    monkeypatch.delenv("CHANNEL_WHATSAPP_ENABLED", raising=False)
    assert active_channels() == ("email", "telegram", "whatsapp")


def test_a_channel_counts_as_connected_only_with_an_address(sync_sessions):
    """The same three attributes `_notify_user` checks before handing anything
    to a transport — so "the screen says connected" and "the worker will send"
    cannot drift apart."""
    from app.core.notification_prefs import connected_channels

    user = _user(sync_sessions)
    assert connected_channels(user) == {
        "email": True,
        "telegram": True,
        "whatsapp": False,
    }

    bare = _user(sync_sessions, telegram_chat_id=None)
    assert connected_channels(bare)["telegram"] is False


# ── what a client may write ──────────────────────────────────────────────────


def test_sanitize_drops_what_it_does_not_know():
    """An older or newer client sends stale keys. Failing the whole write over
    one would break the screen for everybody mid-rollout."""
    from app.core.notification_prefs import sanitize

    assert sanitize(
        {
            "deal": {"email": False, "carrier_pigeon": True},
            "invented": {"email": False},
        }
    ) == {"deal": {"email": False}}


def test_sanitize_drops_a_write_to_a_locked_class():
    from app.core.notification_prefs import sanitize

    assert sanitize({"security": {"email": False}}) == {}


def test_sanitize_refuses_a_value_that_is_not_a_boolean():
    """A stale key is an old client; a string here is a client that has
    misunderstood the field, and it is told so."""
    from app.core.notification_prefs import sanitize

    with pytest.raises(ValueError):
        sanitize({"deal": {"email": "yes"}})


def test_merge_keeps_the_rows_a_write_did_not_mention():
    """One click must not erase a row this screen is not even showing."""
    from app.core.notification_prefs import merged

    assert merged(
        {"deal": {"email": False, "telegram": True}, "deadline": {"email": False}},
        {"deal": {"telegram": False}},
    ) == {
        "deal": {"email": False, "telegram": False},
        "deadline": {"email": False},
    }


# ── the API ──────────────────────────────────────────────────────────────────


async def test_me_answers_with_the_matrix_filled_in(client):
    """The stored column is partial; what leaves the server is not."""
    email = unique_email("prefs-me")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    prefs = resp.json()["notification_prefs"]

    assert set(prefs) == {"deal", "deadline", "security"}
    assert set(prefs["deal"]) == {"email", "telegram", "whatsapp"}
    assert prefs["deal"]["email"] is True
    assert resp.json()["notification_locked"] == ["security"]
    # The account has an address only on mail, so that is the only column the
    # screen may let anybody click.
    assert resp.json()["notification_channels"] == {
        "email": True,
        "telegram": False,
        "whatsapp": False,
    }


async def test_one_cell_can_be_written_on_its_own(client):
    email = unique_email("prefs-patch")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.patch(
        "/api/auth/me",
        json={"notification_prefs": {"deal": {"telegram": False}}},
        headers=headers,
    )
    assert resp.status_code == 200
    prefs = resp.json()["notification_prefs"]
    assert prefs["deal"]["telegram"] is False
    assert prefs["deal"]["email"] is True, "the cell next to it was not touched"
    assert prefs["deadline"]["telegram"] is True, "the row below was not touched"


async def test_a_second_write_does_not_undo_the_first(client):
    """The merge, seen from outside: two clicks on two rows both survive."""
    email = unique_email("prefs-merge")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.patch(
        "/api/auth/me",
        json={"notification_prefs": {"deal": {"telegram": False}}},
        headers=headers,
    )
    resp = await client.patch(
        "/api/auth/me",
        json={"notification_prefs": {"deadline": {"email": False}}},
        headers=headers,
    )

    prefs = resp.json()["notification_prefs"]
    assert prefs["deal"]["telegram"] is False
    assert prefs["deadline"]["email"] is False


async def test_a_write_to_security_changes_nothing(client):
    email = unique_email("prefs-locked")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]

    resp = await client.patch(
        "/api/auth/me",
        json={"notification_prefs": {"security": {"email": False}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["notification_prefs"]["security"]["email"] is True


async def test_the_letter_language_can_be_set_and_is_answered(client):
    """T3.33 — the switcher writes this, and `/me` reads it back so the switcher
    can tell "already this" from "change"."""
    email = unique_email("prefs-locale")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.patch("/api/auth/me", json={"locale": "pl"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["locale"] == "pl"
    assert (await client.get("/api/auth/me", headers=headers)).json()["locale"] == "pl"


async def test_a_regional_tag_is_narrowed_to_the_language(client):
    """`ru-RU` is what a browser reports, and it means a language we have."""
    email = unique_email("prefs-regional")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]

    resp = await client.patch(
        "/api/auth/me",
        json={"locale": "ru-RU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["locale"] == "ru"


async def test_a_language_we_do_not_write_in_is_refused(client):
    """The renderer would fall back to English and the column would claim the
    person had chosen Japanese. A preference that is never honoured is worse
    than no preference."""
    email = unique_email("prefs-unknown")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]

    resp = await client.patch(
        "/api/auth/me",
        json={"locale": "jp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_a_malformed_write_is_refused(client):
    email = unique_email("prefs-bad")
    await make_account(
        {"email": email, "password": SEED_PASSWORD, "display_name": "M"}
    )
    token = (
        await client.post("/api/auth/login", json={"login": email, "password": SEED_PASSWORD})
    ).json()["access_token"]

    resp = await client.patch(
        "/api/auth/me",
        json={"notification_prefs": {"deal": {"email": "yes"}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
