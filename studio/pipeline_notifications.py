from __future__ import annotations

import contextlib
from typing import Any

import httpx

from core_ui.services.notification_config import load_notification_config


def _load_notif_cfg() -> dict[str, Any]:
    """Load Studio notification config with a settings fallback."""
    try:
        cfg = load_notification_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        pass

    try:
        from django.conf import settings

        return {
            "telegram_bot_token": getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "",
            "telegram_chat_id": getattr(settings, "TELEGRAM_CHAT_ID", "") or "",
            "notify_email": getattr(settings, "PIPELINE_NOTIFY_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "") or "",
            "smtp_host": getattr(settings, "EMAIL_HOST", "") or "",
            "smtp_user": getattr(settings, "EMAIL_HOST_USER", "") or "",
            "smtp_password": getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
            "from_email": getattr(settings, "DEFAULT_FROM_EMAIL", "") or "",
            "site_url": getattr(settings, "SITE_URL", "http://localhost:8000") or "http://localhost:8000",
        }
    except Exception:
        return {}


def _global_tg_defaults() -> tuple[str, str]:
    cfg = _load_notif_cfg()
    return str(cfg.get("telegram_bot_token") or ""), str(cfg.get("telegram_chat_id") or "")


def _resolve_telegram_target(
    config: dict[str, Any] | None,
    *,
    token_keys: tuple[str, ...],
    chat_keys: tuple[str, ...],
) -> tuple[str, str]:
    node_config = config if isinstance(config, dict) else {}
    global_token, global_chat = _global_tg_defaults()

    def _first_non_empty(keys: tuple[str, ...], fallback: str) -> str:
        for key in keys:
            value = str(node_config.get(key) or "").strip()
            if value:
                return value
        return str(fallback or "").strip()

    return (
        _first_non_empty(token_keys, global_token),
        _first_non_empty(chat_keys, global_chat),
    )


def _global_email_defaults() -> tuple[str, str, str, str, str]:
    cfg = _load_notif_cfg()
    return (
        str(cfg.get("notify_email") or ""),
        str(cfg.get("smtp_host") or ""),
        str(cfg.get("smtp_user") or ""),
        str(cfg.get("smtp_password") or ""),
        str(cfg.get("from_email") or ""),
    )


def _global_site_url() -> str:
    cfg = _load_notif_cfg()
    return str(cfg.get("site_url") or "http://localhost:8000").rstrip("/")


def _resolve_from_email(from_email: str, smtp_user: str, smtp_host: str) -> str:
    if not from_email or "weuai.site" in from_email or "noreply@" in (from_email or "").lower():
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
    to_email = (to_email or "").strip()
    if not to_email or "@" in to_email:
        return to_email
    host = (smtp_host or "").lower()
    if "yandex" in host:
        return f"{to_email}@yandex.ru"
    if "gmail" in host:
        return f"{to_email}@gmail.com"
    return to_email


async def _send_telegram_message(
    *,
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "Markdown",
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = False,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)] or [""]
    sent = 0
    message_ids: list[int] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if disable_web_page_preview:
                payload["disable_web_page_preview"] = True
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup

            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                err = str(resp.text or "")[:200]
                return {"status": "failed", "error": f"Telegram API error {resp.status_code}: {err}"}
            with contextlib.suppress(Exception):
                resp_payload = resp.json()
                message_id = int(((resp_payload.get("result") or {}) or {}).get("message_id"))
                message_ids.append(message_id)
            sent += 1

    return {
        "status": "completed",
        "output": f"📱 Telegram message sent to {chat_id} ({sent} chunk(s))",
        "message_ids": message_ids,
        "last_message_id": message_ids[-1] if message_ids else None,
    }
