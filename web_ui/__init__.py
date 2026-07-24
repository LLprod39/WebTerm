"""
WebTerm Platform Django project.
"""

# Import Celery app so it's loaded when Django starts.
# In minimal environments Celery may be absent; Django should still boot.
try:
    from web_ui.celery import app as celery_app
except Exception:  # pragma: no cover - fallback for mini installs
    celery_app = None

__all__ = ("celery_app",)
