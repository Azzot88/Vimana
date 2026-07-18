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
}
celery_app.conf.task_routes = {
    "app.tasks.notifications.*": {"queue": "notifications"},
    "app.tasks.uba.*": {"queue": "notifications"},
}
