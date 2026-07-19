"""
Production settings.

Inherits all configuration from base.py.
base.py enforces production guards when DJANGO_DEBUG=false:
  - SECRET_KEY must be set and strong
  - ALLOWED_HOSTS must be configured
  - CHANNEL_REDIS_URL must be set
  - CELERY_TASK_ALWAYS_EAGER is NOT set (tasks run via real Celery workers)

Usage (docker-compose.production.yml / Render / any cloud):
    DJANGO_SETTINGS_MODULE=web_ui.settings.production
    DJANGO_DEBUG=false
    DJANGO_SECRET_KEY=<strong-random-key>
    ALLOWED_HOSTS=yourdomain.com
    CHANNEL_REDIS_URL=redis://redis:6379/1
"""
import os

from web_ui.settings.base import *  # noqa: F401, F403
from web_ui.settings.base import DEBUG

# Explicitly enforce production mode — fail fast if DEBUG is accidentally True.
if DEBUG:
    raise RuntimeError(
        "web_ui.settings.production loaded but DEBUG=True. "
        "Set DJANGO_DEBUG=false in your environment."
    )

# Managed secrets (SSH/sudo passwords, LLM API keys, k8s tokens) are encrypted with a
# key derived from MANAGED_SECRET_KEY. Without a dedicated key it falls back to the
# Django SECRET_KEY, coupling secret encryption to the signing key. Refuse that in
# production unless the operator explicitly opts in for a migration window.
_has_managed_secret_key = bool(
    (os.getenv("MANAGED_SECRET_KEY") or os.getenv("APP_SECRET_ENCRYPTION_KEY") or "").strip()
)
_allow_secret_key_fallback = (
    os.getenv("ALLOW_SECRET_KEY_MANAGED_ENCRYPTION", "") or ""
).strip().lower() in {"1", "true", "yes", "on"}
if not _has_managed_secret_key and not _allow_secret_key_fallback:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "MANAGED_SECRET_KEY (or APP_SECRET_ENCRYPTION_KEY) must be set in production so that "
        "stored secrets are not encrypted with the Django SECRET_KEY. Set a dedicated random "
        "key, or set ALLOW_SECRET_KEY_MANAGED_ENCRYPTION=true to opt out during migration."
    )
