"""
Studio notification settings and test endpoints.
"""

import asyncio
import json
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import httpx
from django.conf import settings as django_settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from core_ui.services.notification_config import (
    _NOTIF_CONFIG_PATH as _DEFAULT_NOTIF_CONFIG_PATH,
)
from core_ui.services.notification_config import (
    _NOTIF_DEFAULTS,
    load_notification_config,
    notif_config_path,
    save_notification_config,
)

STUDIO_FEATURE_NOTIFICATIONS = "studio_notifications"
_NOTIF_CONFIG_PATH = _DEFAULT_NOTIF_CONFIG_PATH


def _notif_config_path() -> Path:
    return notif_config_path(_NOTIF_CONFIG_PATH)


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _require_admin(request, *, message: str = "Admin access required") -> JsonResponse | None:
    if getattr(request.user, "is_staff", False):
        return None
    return _err(message, 403)


def _load_notif_config() -> dict:
    """Read notification config from file; fall back to Django / env defaults."""
    return load_notification_config(_notif_config_path())


def _save_notif_config(data: dict):
    """Persist notification config values."""
    save_notification_config(data, _notif_config_path())


def _resolve_from_email_smtp(from_email: str, smtp_user: str, smtp_host: str) -> str:
    """Use real mailbox as From when default is noreply-like or otherwise broken."""
    if not from_email or "noreply@" in (from_email or "").lower():
        if not smtp_user:
            return from_email or "pipeline@noreply.local"
        user = (smtp_user or "").strip()
        if "@" in user:
            return user
        host = (smtp_host or "").lower()
        if "yandex" in host:
            return f"{user}@yandex.ru"
        if "gmail" in host:
            return f"{user}@gmail.com"
        return user
    return from_email


def _normalize_email_recipient(to_email: str, smtp_host: str) -> str:
    """If recipient is only login, append domain for Yandex/Gmail."""
    to_email = (to_email or "").strip()
    if not to_email or "@" in to_email:
        return to_email
    host = (smtp_host or "").lower()
    if "yandex" in host:
        return f"{to_email}@yandex.ru"
    if "gmail" in host:
        return f"{to_email}@gmail.com"
    return to_email


@require_feature(STUDIO_FEATURE_NOTIFICATIONS)
def api_notification_settings(request):
    """
    GET  /api/studio/notifications/  - return current notification settings.
    POST /api/studio/notifications/  - save notification settings.
    """
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error

    if request.method == "GET":
        cfg = _load_notif_config()
        masked = dict(cfg)
        if masked.get("smtp_password"):
            masked["smtp_password"] = "••••••••"
        if masked.get("telegram_bot_token") and len(masked["telegram_bot_token"]) > 10:
            token = masked["telegram_bot_token"]
            masked["telegram_bot_token"] = token[:8] + "•" * (len(token) - 8)
        return _ok(masked)

    if request.method == "POST":
        data = _json_body(request)
        allowed = set(_NOTIF_DEFAULTS.keys())
        to_save = {key: value for key, value in data.items() if key in allowed}
        if to_save.get("smtp_password", "").startswith("•"):
            existing = _load_notif_config()
            to_save["smtp_password"] = existing.get("smtp_password", "")
        if to_save.get("telegram_bot_token", "").endswith("•" * 4):
            existing = _load_notif_config()
            to_save["telegram_bot_token"] = existing.get("telegram_bot_token", "")
        _save_notif_config(to_save)
        return _ok({"ok": True, "saved": list(to_save.keys())})

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_NOTIFICATIONS)
@require_http_methods(["POST"])
def api_notification_test_telegram(request):
    """POST /api/studio/notifications/test-telegram/ - send a test Telegram message."""
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error

    cfg = _load_notif_config()
    bot_token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()

    if not bot_token or not chat_id:
        return _err("Telegram bot_token and chat_id must be configured first.")

    async def _send():
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "✅ *WEU Platform* — Telegram notifications are working correctly!",
                    "parse_mode": "Markdown",
                },
            )
            return resp.status_code, resp.text[:300]

    try:
        code, body = asyncio.run(_send())
        if code == 200:
            return _ok({"ok": True, "message": f"Test message sent to chat {chat_id}"})
        return _err(f"Telegram API returned {code}: {body}")
    except Exception as exc:
        return _err(f"Send failed: {exc}")


@require_feature(STUDIO_FEATURE_NOTIFICATIONS)
@require_http_methods(["POST"])
def api_notification_test_email(request):
    """POST /api/studio/notifications/test-email/ - send a test email."""
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error

    cfg = _load_notif_config()
    to_email = cfg.get("notify_email", "").strip()
    smtp_host = cfg.get("smtp_host", "").strip() or getattr(django_settings, "EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(cfg.get("smtp_port") or getattr(django_settings, "EMAIL_PORT", 587))
    smtp_user = cfg.get("smtp_user", "").strip() or getattr(django_settings, "EMAIL_HOST_USER", "")
    smtp_password = cfg.get("smtp_password", "").strip() or getattr(django_settings, "EMAIL_HOST_PASSWORD", "")
    from_email = (
        cfg.get("from_email", "").strip()
        or smtp_user
        or getattr(django_settings, "DEFAULT_FROM_EMAIL", "")
        or "pipeline@noreply.local"
    )
    from_email = _resolve_from_email_smtp(from_email, smtp_user, smtp_host)
    to_email = _normalize_email_recipient(to_email, smtp_host)

    if not to_email:
        return _err("notify_email is not configured.")
    if not smtp_user:
        return _err("smtp_user (email login) is not configured.")

    try:
        msg = MIMEText("✅ WEU Platform — Email notifications are working correctly!", "plain", "utf-8")
        msg["Subject"] = "WEU Platform — Test Email"
        msg["From"] = from_email
        msg["To"] = to_email

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                if smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())

        return _ok({"ok": True, "message": f"Test email sent to {to_email}"})
    except Exception as exc:
        return _err(f"SMTP error: {exc}")
