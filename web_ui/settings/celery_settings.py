from __future__ import annotations

import os


def build_celery_settings(*, debug: bool, time_zone: str) -> dict[str, object]:
    settings: dict[str, object] = {
        "CELERY_BROKER_URL": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        "CELERY_RESULT_BACKEND": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        "CELERY_ACCEPT_CONTENT": ["json"],
        "CELERY_TASK_SERIALIZER": "json",
        "CELERY_RESULT_SERIALIZER": "json",
        "CELERY_TIMEZONE": time_zone,
        "CELERY_ENABLE_UTC": True,
        "CELERY_TASK_TRACK_STARTED": True,
        "CELERY_TASK_TIME_LIMIT": 30 * 60,
        "CELERY_TASK_SOFT_TIME_LIMIT": 25 * 60,
        "CELERY_RESULT_EXPIRES": 60 * 60 * 24,
        "CELERY_WORKER_PREFETCH_MULTIPLIER": 1,
        "CELERY_WORKER_CONCURRENCY": int(os.getenv("CELERY_WORKER_CONCURRENCY", "4")),
        "CELERY_TASK_ROUTES": {},
    }
    if debug and not os.getenv("CELERY_TASK_ALWAYS_EAGER", "").strip():
        settings["CELERY_TASK_ALWAYS_EAGER"] = True
        settings["CELERY_TASK_EAGER_PROPAGATES"] = True
    return settings
