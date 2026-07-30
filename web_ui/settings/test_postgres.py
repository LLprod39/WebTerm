"""CI settings for the full backend suite backed by real PostgreSQL and Redis.

SQLite remains available through ``web_ui.settings.test`` for fast local loops.
It cannot exercise PostgreSQL row locks, ``skip_locked`` or advisory locks, so
release and concurrency evidence must use this settings module.
"""

from web_ui.settings.database import build_channel_settings, build_database_settings
from web_ui.settings.test import *  # noqa: F401, F403

DATABASES = build_database_settings(base_dir=BASE_DIR)["DATABASES"]  # noqa: F405
# The Django test runner owns transaction-scoped connections for the duration
# of the suite. Production still uses the 60-second default; disabling age-out
# here prevents close_old_connections() in worker-path tests from invalidating
# the runner's enclosing transaction after a long suite.
DATABASES["default"]["CONN_MAX_AGE"] = None
globals().update(build_channel_settings(debug=False))

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CHANNEL_REDIS_URL,  # noqa: F405
        "TIMEOUT": 300,
    }
}
