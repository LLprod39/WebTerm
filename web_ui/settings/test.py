"""
Test settings for pytest / CI.

Usage (pyproject.toml):
    DJANGO_SETTINGS_MODULE = "web_ui.settings.test"

Overrides vs development:
  - PASSWORD_HASHERS: fastest hasher for speed
  - CELERY_TASK_ALWAYS_EAGER: True (no broker needed)
  - EMAIL_BACKEND: locmem (no real emails)
  - CHANNEL_LAYERS: InMemoryChannelLayer (no Redis needed)
  - MEDIA_ROOT: temp dir to avoid polluting dev media/
"""
import tempfile

from web_ui.settings.development import *  # noqa: F401, F403

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Never send real emails during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Always run Celery tasks synchronously — no broker required
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Use in-memory channel layer — no Redis required
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# Isolate uploaded files from dev workspace
MEDIA_ROOT = tempfile.mkdtemp(prefix="weu_test_media_")
