"""
Celery configuration for WEU AI Platform.

Usage:
    # Start worker:
    celery -A web_ui worker -l info

    # Start beat (for periodic tasks):
    celery -A web_ui beat -l info

    # Start both in dev (not recommended for production):
    celery -A web_ui worker -B -l info
"""
import os

from celery import Celery

# Set default Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings.development")

app = Celery("weu_platform")

# Load config from Django settings with CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all registered Django apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f"Request: {self.request!r}")
