from celery import Celery
from app.core.config import settings

celery_app = Celery("vimana", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

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
