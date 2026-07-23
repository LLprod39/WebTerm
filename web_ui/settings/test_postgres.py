"""CI integration settings backed by real PostgreSQL, Redis cache and channels."""

from web_ui.settings.database import build_channel_settings, build_database_settings
from web_ui.settings.test import *  # noqa: F401, F403

DATABASES = build_database_settings(base_dir=BASE_DIR)["DATABASES"]  # noqa: F405
globals().update(build_channel_settings(debug=False))

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CHANNEL_REDIS_URL,  # noqa: F405
        "TIMEOUT": 300,
    }
}
