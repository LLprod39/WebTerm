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
