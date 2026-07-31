from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

from django.conf import settings as django_settings

from core_ui.managed_secrets import get_notification_secret, set_notification_secret

_NOTIF_CONFIG_PATH = Path(getattr(django_settings, "BASE_DIR", ".")) / ".notification_config.json"
_NOTIF_SECRET_KEYS = {"telegram_bot_token", "smtp_password"}

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


def notif_config_path(override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    env_path = (os.getenv("NOTIFICATION_CONFIG_PATH") or "").strip()
    if env_path:
        return Path(env_path)
    return _NOTIF_CONFIG_PATH


def _base_notification_config() -> dict[str, Any]:
    return {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "")
        or getattr(django_settings, "TELEGRAM_BOT_TOKEN", "")
        or "",
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "") or getattr(django_settings, "TELEGRAM_CHAT_ID", "") or "",
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


def _read_saved_notification_config(config_path: str | Path | None = None) -> dict[str, Any]:
    config_path = notif_config_path(config_path)
    if config_path.exists():
        with contextlib.suppress(Exception):
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                return saved
    return {}


def _managed_notification_secret(key: str) -> str:
    with contextlib.suppress(Exception):
        return get_notification_secret(key)
    return ""


def load_notification_config(config_path: str | Path | None = None) -> dict[str, Any]:
    base = _base_notification_config()
    saved = _read_saved_notification_config(config_path)
    for key, value in saved.items():
        if key in base and key not in _NOTIF_SECRET_KEYS and value:
            base[key] = value
    for key in _NOTIF_SECRET_KEYS:
        managed_value = _managed_notification_secret(key)
        if managed_value:
            base[key] = managed_value
        elif saved.get(key):
            # Legacy fallback: older installs stored notification secrets in
            # .notification_config.json. New writes move them into ManagedSecret.
            base[key] = str(saved.get(key) or "")
    return base


def save_notification_config(data: dict[str, Any], config_path: str | Path | None = None) -> None:
    existing = {
        key: value
        for key, value in _read_saved_notification_config(config_path).items()
        if key in _NOTIF_DEFAULTS and key not in _NOTIF_SECRET_KEYS
    }
    for key in _NOTIF_DEFAULTS:
        if key in data:
            if key in _NOTIF_SECRET_KEYS:
                set_notification_secret(key, str(data.get(key) or ""))
            else:
                existing[key] = data[key]
    config_path = notif_config_path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
