"""Celery wiring — every task the system dispatches must actually be registered.

Found the hard way on 2026-07-27: `celery -A app.worker.celery_app` imports only
`app/worker.py`, which pulled in no task module at all. The worker ran with an
empty registry and answered every dispatch with `Received unregistered task`.
Beat kept emitting on schedule; the messages were dropped. Nothing had ever run
— notifications, UBA recompute, relay whitelist, e2e cleanup, chain anchoring —
and nothing said so, because a rejected task is a log line on the worker, not an
error where it was dispatched.

These tests are cheap and would have caught it the day it appeared.
"""
import pytest

from app.worker import celery_app

# Dispatched from request handlers or other tasks rather than from the beat
# schedule, so `beat_schedule` alone would not cover them.
DISPATCHED_BY_CODE = [
    "app.tasks.notifications.send_verification_code",
    "app.tasks.notifications.notify_deal_status",
    "app.tasks.notifications.send_waitlist_emails",
    "app.tasks.notifications.send_telegram_chat",
    "app.tasks.notifications.send_password_reset",
    # Run by hand after deploy, not from the beat schedule — but it is still
    # dispatched by name, and an unregistered name fails the same way.
    "app.tasks.notifications.send_pending_waitlist_confirmations",
    "app.tasks.nostr_publish.publish_trip_to_nostr",
    "app.tasks.nostr_publish.delete_trip_from_nostr",
]


def test_beat_schedule_is_not_empty():
    """Guards the guard: an empty schedule would make the test below vacuous."""
    assert celery_app.conf.beat_schedule


@pytest.mark.parametrize(
    "task_name",
    sorted({entry["task"] for entry in celery_app.conf.beat_schedule.values()}),
)
def test_scheduled_task_is_registered(task_name):
    assert task_name in celery_app.tasks, (
        f"{task_name} is scheduled but not registered — beat will emit it and "
        "the worker will drop it. Add its module to `_TASK_MODULES` in "
        "app/worker.py."
    )


@pytest.mark.parametrize("task_name", DISPATCHED_BY_CODE)
def test_dispatched_task_is_registered(task_name):
    assert task_name in celery_app.tasks, (
        f"{task_name} is dispatched from application code but not registered. "
        "Add its module to `_TASK_MODULES` in app/worker.py."
    )


def test_every_task_module_is_included():
    """Catches a new module under `app/tasks/` that nobody wired up."""
    import pkgutil

    import app.tasks

    from app.worker import _TASK_MODULES

    found = {
        f"app.tasks.{m.name}"
        for m in pkgutil.iter_modules(app.tasks.__path__)
        if not m.name.startswith("_")
    }
    missing = found - set(_TASK_MODULES)
    assert not missing, (
        f"task modules not included in the Celery app: {sorted(missing)}. "
        "Their tasks would be dropped by the worker."
    )


def test_every_listed_module_is_actually_imported():
    """T3.8 — `_TASK_MODULES` must import, not merely enumerate.

    Celery's `include=` was set for six modules and imported none of them. The
    registry looked healthy anyway because the API imports `notifications`, the
    UBA endpoint imports `uba`, and so on — every task module happened to have
    a caller. `malware_rescan` was the first without one (beat is its only
    user), and it surfaced as "scheduled but not registered".

    This asserts the mechanism rather than the outcome: a module in the list is
    in `sys.modules` after importing `app.worker`, whether or not anything else
    in the app happens to want it.
    """
    import sys

    from app.worker import _TASK_MODULES

    missing = [m for m in _TASK_MODULES if m not in sys.modules]
    assert not missing, f"listed but never imported: {missing}"
