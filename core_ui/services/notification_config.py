from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from django.conf import settings as django_settings

_NOTIF_CONFIG_PATH = Path(getattr(django_settings, "BASE_DIR", ".")) / ".notification_config.json"

_NOTIF_DEFAULTS = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "notify_email": "",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "from_email": "",
    "site_url": "",
}


def notif_config_path() -> Path:
    package = sys.modules.get("studio.views")
    return Path(getattr(package, "_NOTIF_CONFIG_PATH", _NOTIF_CONFIG_PATH))


def load_notification_config() -> dict[str, Any]:
    base: dict[str, Any] = {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "")
        or getattr(django_settings, "TELEGRAM_BOT_TOKEN", "")
        or "",
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "")
        or getattr(django_settings, "TELEGRAM_CHAT_ID", "")
        or "",
        "notify_email": (
            os.getenv("PIPELINE_NOTIFY_EMAIL", "")
            or getattr(django_settings, "PIPELINE_NOTIFY_EMAIL", "")
            or os.getenv("EMAIL_HOST_USER", "")
            or getattr(django_settings, "EMAIL_HOST_USER", "")
            or ""
        ),
        "smtp_host": getattr(django_settings, "EMAIL_HOST", "smtp.gmail.com") or "",
        "smtp_port": str(getattr(django_settings, "EMAIL_PORT", 587)),
        "smtp_user": getattr(django_settings, "EMAIL_HOST_USER", "") or "",
        "smtp_password": getattr(django_settings, "EMAIL_HOST_PASSWORD", "") or "",
        "from_email": getattr(django_settings, "DEFAULT_FROM_EMAIL", "") or "",
        "site_url": getattr(django_settings, "SITE_URL", "http://localhost:8000") or "http://localhost:8000",
    }
    config_path = notif_config_path()
    if config_path.exists():
        with contextlib.suppress(Exception):
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in saved.items():
                if key in base and value:
                    base[key] = value
    return base


def save_notification_config(data: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    config_path = notif_config_path()
    if config_path.exists():
        with contextlib.suppress(Exception):
            existing = json.loads(config_path.read_text(encoding="utf-8"))
    for key in _NOTIF_DEFAULTS:
        if key in data:
            existing[key] = data[key]
    config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
