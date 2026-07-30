"""
Test settings for pytest / CI.

Usage (pyproject.toml):
    DJANGO_SETTINGS_MODULE = "web_ui.settings.test"

Overrides vs development:
  - PASSWORD_HASHERS: fastest hasher for speed
  - CELERY_TASK_ALWAYS_EAGER: True (no broker needed)
  - EMAIL_BACKEND: locmem (no real emails)
  - CHANNEL_LAYERS: InMemoryChannelLayer (no Redis needed)
  - MEDIA_ROOT / PLAYBOOK_BUNDLE_STORAGE_ROOT: temp dirs to avoid polluting dev storage
"""

import tempfile
from pathlib import Path

from web_ui.settings.development import *  # noqa: F401, F403

TEST_ARTIFACT_ROOT = Path(tempfile.mkdtemp(prefix="weu_test_"))
TESTING = True

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Never send real emails during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Always run Celery tasks synchronously — no broker required
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
LLM_USAGE_SKIP_DETACHED_SQLITE_LOGGING = False
PIPELINE_RUNS_DISABLE_BACKGROUND = True
MARS_AGENT_RUNTIME = "host"
MARS_ALLOW_UNSAFE_HOST_RUNTIME_FOR_TESTS = True
# Admin Mode is disabled by default in every runtime. Tests opt in explicitly
# so the existing guarded Admin contracts remain covered without widening v0.1.
KUBERNETES_ADMIN_MODE_ENABLED = True

# Use in-memory channel layer — no Redis required
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "webterm-test-cache",
        "TIMEOUT": 300,
    }
}

# Isolate uploaded files from dev workspace
MEDIA_ROOT = TEST_ARTIFACT_ROOT / "media"
PLAYBOOK_BUNDLE_STORAGE_ROOT = TEST_ARTIFACT_ROOT / "private" / "playbook_bundles"

# Plugin package fixtures in tests are staged from this fake host.
# Deploy-check tests that assert the unset-allowlist errors override this
# explicitly with override_settings(...=[]).
PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS = ["packages.example"]

# Keep tests self-contained even when .env points development at PostgreSQL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": TEST_ARTIFACT_ROOT / "db.sqlite3",
        "OPTIONS": {
            "timeout": 60,
        },
    }
}
