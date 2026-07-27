from celery import Celery
from app.core.config import settings

# `celery -A app.worker.celery_app` imports *this* module and nothing else, so a
# task is only registered if something pulls its module in. Nothing did:
# `app/tasks/__init__.py` is empty and neither `include` nor
# `autodiscover_tasks` was set, so the worker came up with an empty registry and
# answered every dispatch with `Received unregistered task`. Beat kept emitting
# on schedule and the worker kept dropping the messages — which is why no
# notification, UBA recompute, relay-whitelist refresh, e2e cleanup or chain
# anchor has ever actually run in this deployment (found 2026-07-27, chasing a
# confirmation email that never arrived).
#
# Every new module under `app/tasks/` has to be listed here. `test_worker.py`
# asserts that everything referenced by `beat_schedule` or dispatched from the
# API is registered, so the next omission fails a test instead of going quiet.
_TASK_MODULES = [
    "app.tasks.notifications",
    "app.tasks.uba",
    "app.tasks.cleanup",
    "app.tasks.nostr_publish",
    "app.tasks.nostr_whitelist",
    "app.tasks.chain_anchor",
]

celery_app = Celery(
    "vimana",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=_TASK_MODULES,
)

celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "check-upcoming-deadlines": {
        "task": "app.tasks.notifications.check_upcoming_deadlines",
        "schedule": 3600.0,
    },
    "recompute-uba-hourly": {
        "task": "app.tasks.uba.recompute_all_uba",
        "schedule": 3600.0,
    },
    "refresh-nostr-whitelist-hourly": {
        "task": "app.tasks.nostr_whitelist.refresh_allowed_pubkeys",
        "schedule": 3600.0,
    },
    "cleanup-e2e-users-daily": {
        "task": "app.tasks.cleanup.cleanup_e2e_users",
        "schedule": 86400.0,
    },
    # T3.6 — head-only, so one tick costs one event per deal that moved.
    "anchor-deal-chains-hourly": {
        "task": "app.tasks.chain_anchor.anchor_deal_chains",
        "schedule": 3600.0,
    },
}
celery_app.conf.task_routes = {
    "app.tasks.notifications.*": {"queue": "notifications"},
    "app.tasks.uba.*": {"queue": "notifications"},
    "app.tasks.nostr_whitelist.*": {"queue": "notifications"},
    "app.tasks.cleanup.*": {"queue": "notifications"},
    "app.tasks.chain_anchor.*": {"queue": "notifications"},
}
