from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.conf import settings
from loguru import logger

from app.core.model_config import model_manager
from app.core.provider_registry import get_provider_registry
from core_ui.managed_secrets import (
    list_undecryptable_secrets,
    managed_secret_key_source,
    verify_managed_secret_roundtrip,
)
from core_ui.services.notification_config import load_notification_config, notif_config_path
from web_ui.services.settings_readiness_common import (
    has_value,
    is_placeholder,
    readiness_check,
    safe_resolved_path,
)


def deployment_mode_check() -> dict[str, Any]:
    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    details = {"debug": bool(settings.DEBUG), "allowed_hosts": allowed_hosts}
    if settings.DEBUG:
        return readiness_check(
            "deployment_mode",
            "Режим Django",
            "warning",
            "DJANGO_DEBUG включен. Для первого внутреннего PROD-запуска нужно запускать с DJANGO_DEBUG=false.",
            details=details,
        )
    if not allowed_hosts or "*" in allowed_hosts:
        return readiness_check(
            "deployment_mode",
            "Режим Django",
            "error",
            "DEBUG выключен, но ALLOWED_HOSTS пустой или слишком широкий.",
            details=details,
        )
    return readiness_check(
        "deployment_mode",
        "Режим Django",
        "ready",
        "Django запущен в production-режиме с ограниченным ALLOWED_HOSTS.",
        details=details,
    )


def placeholder_secret_check() -> dict[str, Any]:
    values = {
        "DJANGO_SECRET_KEY": os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY") or "",
        "MANAGED_SECRET_KEY": os.getenv("MANAGED_SECRET_KEY") or os.getenv("APP_SECRET_ENCRYPTION_KEY") or "",
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD") or "",
    }
    placeholders = [name for name, value in values.items() if is_placeholder(value)]
    missing_for_prod = [name for name in ("DJANGO_SECRET_KEY", "MANAGED_SECRET_KEY") if not has_value(values[name])]
    details = {
        "placeholder_names": placeholders,
        "missing_for_prod": missing_for_prod,
        "postgres_password_set": has_value(values["POSTGRES_PASSWORD"]),
    }
    if placeholders:
        return readiness_check(
            "secret_placeholders",
            "Environment secrets",
            "error",
            "В env остались placeholder secret values: " + ", ".join(placeholders) + ".",
            details=details,
        )
    if not settings.DEBUG and missing_for_prod:
        return readiness_check(
            "secret_placeholders",
            "Environment secrets",
            "error",
            "Для production отсутствуют обязательные secrets: " + ", ".join(missing_for_prod) + ".",
            details=details,
        )
    if missing_for_prod:
        return readiness_check(
            "secret_placeholders",
            "Environment secrets",
            "warning",
            "Для будущего production запуска нужно задать: " + ", ".join(missing_for_prod) + ".",
            details=details,
        )
    return readiness_check(
        "secret_placeholders",
        "Environment secrets",
        "ready",
        "Ключевые env secrets заданы и не похожи на placeholders.",
        details=details,
    )


def managed_secret_check() -> dict[str, Any]:
    source = managed_secret_key_source()
    try:
        roundtrip_ok = verify_managed_secret_roundtrip()
    except Exception as exc:
        return readiness_check(
            "managed_secret_key",
            "Ключ шифрования секретов",
            "error",
            f"Managed secrets не проходят проверку шифрования: {exc}",
            details={"key_source": source, "roundtrip_ok": False},
        )
    if not roundtrip_ok:
        return readiness_check(
            "managed_secret_key",
            "Ключ шифрования секретов",
            "error",
            "Managed secrets не проходят encrypt/decrypt roundtrip.",
            details={"key_source": source, "roundtrip_ok": False},
        )
    try:
        undecryptable = list_undecryptable_secrets()
    except Exception as exc:
        logger.debug("Managed secret storage scan failed: {}", exc)
        undecryptable = []
    if undecryptable:
        return readiness_check(
            "managed_secret_key",
            "Ключ шифрования секретов",
            "error",
            f"{len(undecryptable)} сохранённых секретов не расшифровываются текущим ключом. "
            "Ключ менялся после сохранения, либо секреты писал процесс с другим "
            "MANAGED_SECRET_KEY/SECRET_KEY (например web и workers с разным env). "
            "Выровняйте ключ во всех процессах или пересохраните секреты.",
            details={
                "key_source": source,
                "roundtrip_ok": True,
                "undecryptable": undecryptable[:20],
                "undecryptable_count": len(undecryptable),
            },
        )
    if source == "SECRET_KEY":
        return readiness_check(
            "managed_secret_key",
            "Ключ шифрования секретов",
            "error" if not settings.DEBUG else "warning",
            "MANAGED_SECRET_KEY не задан. Секреты шифруются от Django SECRET_KEY, поэтому ротация SECRET_KEY может сломать расшифровку.",
            details={"key_source": source, "roundtrip_ok": True},
        )
    return readiness_check(
        "managed_secret_key",
        "Ключ шифрования секретов",
        "ready",
        f"Managed secrets используют отдельный источник ключа: {source}.",
        details={"key_source": source, "roundtrip_ok": True},
    )


def runtime_config_paths_check() -> dict[str, Any]:
    model_path = model_manager._config_path()
    notification_path = notif_config_path()
    model_env = bool((os.getenv("MODEL_CONFIG_PATH") or "").strip()) and has_value(model_path)
    notification_env = bool((os.getenv("NOTIFICATION_CONFIG_PATH") or "").strip())
    details = {
        "model_config_path": model_path,
        "model_config_env": model_env,
        "notification_config_path": safe_resolved_path(notification_path),
        "notification_config_env": notification_env,
    }
    if model_env and notification_env:
        return readiness_check(
            "runtime_config_paths",
            "Persisted web settings",
            "ready",
            "MODEL_CONFIG_PATH и NOTIFICATION_CONFIG_PATH вынесены в явные runtime paths.",
            details=details,
        )
    missing = []
    if not model_env:
        missing.append("MODEL_CONFIG_PATH")
    if not notification_env:
        missing.append("NOTIFICATION_CONFIG_PATH")
    return readiness_check(
        "runtime_config_paths",
        "Persisted web settings",
        "warning",
        "Часть настроек сохраняется в default path. Для разворачивания лучше задать " + ", ".join(missing) + ".",
        details=details,
    )


def _selected_provider_statuses() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    model_manager.load_config()
    config = model_manager.config
    registry = get_provider_registry()
    roles = {
        "default": getattr(config, "default_provider", "") or "grok",
        "internal": getattr(config, "internal_llm_provider", "") or getattr(config, "default_provider", "") or "grok",
        "chat": getattr(config, "chat_llm_provider", "") or getattr(config, "internal_llm_provider", "") or "grok",
        "agent": getattr(config, "agent_llm_provider", "") or getattr(config, "internal_llm_provider", "") or "grok",
        "orchestrator": getattr(config, "orchestrator_llm_provider", "")
        or getattr(config, "internal_llm_provider", "")
        or "grok",
    }
    available_any = bool(registry.get_available_providers())
    selected: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for role, provider in roles.items():
        provider_key = str(provider or "").strip()
        enabled = available_any if provider_key == "auto" else registry.is_enabled(provider_key)
        configured = available_any if provider_key == "auto" else registry.is_configured(provider_key)
        item = {"role": role, "provider": provider_key, "enabled": enabled, "configured": configured}
        selected.append(item)
        if not (enabled and configured):
            missing.append(item)
    return selected, missing


def ai_provider_check() -> dict[str, Any]:
    try:
        selected, missing = _selected_provider_statuses()
    except Exception as exc:
        return readiness_check(
            "ai_providers",
            "AI providers",
            "error",
            f"Не удалось прочитать настройки AI-провайдеров: {exc}",
            action_path="/settings/ai",
            action_label="Открыть модели",
        )
    configured_count = sum(1 for item in selected if item["enabled"] and item["configured"])
    details = {"selected": selected, "configured_selected_count": configured_count}
    if configured_count == 0:
        return readiness_check(
            "ai_providers",
            "AI providers",
            "error",
            "Ни один выбранный AI provider не готов. Чат, генерация workflow и агенты будут падать.",
            action_path="/settings/ai",
            action_label="Настроить модели",
            details=details,
        )
    if missing:
        roles = ", ".join(f"{item['role']}={item['provider']}" for item in missing)
        return readiness_check(
            "ai_providers",
            "AI providers",
            "warning",
            f"Часть назначенных AI provider не готова: {roles}.",
            action_path="/settings/ai",
            action_label="Проверить модели",
            details=details,
        )
    return readiness_check(
        "ai_providers",
        "AI providers",
        "ready",
        "Все выбранные AI provider включены и имеют runtime/API-key.",
        action_path="/settings/ai",
        action_label="Открыть модели",
        details=details,
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.debug("Failed to inspect JSON config file %s: %s", path, exc)
    return {}


def notification_check() -> dict[str, Any]:
    cfg = load_notification_config()
    config_path = notif_config_path()
    saved = _load_json_file(config_path)
    legacy_secret_keys = [key for key in ("telegram_bot_token", "smtp_password") if has_value(saved.get(key))]
    telegram_ready = has_value(cfg.get("telegram_bot_token")) and has_value(cfg.get("telegram_chat_id"))
    email_ready = (
        has_value(cfg.get("notify_email")) and has_value(cfg.get("smtp_host")) and has_value(cfg.get("smtp_user"))
    )
    explicit_path = bool((os.getenv("NOTIFICATION_CONFIG_PATH") or "").strip())
    details = {
        "telegram_ready": telegram_ready,
        "email_ready": email_ready,
        "site_url_ready": has_value(cfg.get("site_url")),
        "config_path": safe_resolved_path(config_path),
        "config_path_env": explicit_path,
        "legacy_file_secret_key_count": len(legacy_secret_keys),
    }
    if legacy_secret_keys:
        message = "В старом notification JSON ещё есть секретные поля. Следующее сохранение через UI перенесёт их в ManagedSecret."
    elif not (telegram_ready or email_ready):
        message = "Не настроен ни Telegram, ни Email. Согласования и алерты не смогут отправлять внешние уведомления."
    elif not details["site_url_ready"] or not explicit_path:
        message = "Канал уведомлений есть, но проверьте публичный URL и NOTIFICATION_CONFIG_PATH для production."
    else:
        return readiness_check(
            "notifications",
            "Уведомления",
            "ready",
            "Есть готовый канал уведомлений и runtime path для notification config.",
            action_path="/settings/notifications",
            action_label="Открыть уведомления",
            details=details,
        )
    return readiness_check(
        "notifications",
        "Уведомления",
        "warning",
        message,
        action_path="/settings/notifications",
        action_label="Открыть уведомления",
        details=details,
    )


def domain_auth_check() -> dict[str, Any]:
    model_manager.load_config()
    config = model_manager.config
    enabled = (
        getattr(config, "domain_auth_enabled", None)
        if getattr(config, "domain_auth_enabled", None) is not None
        else bool(getattr(settings, "DOMAIN_AUTH_ENABLED", False))
    )
    header = getattr(config, "domain_auth_header", None) or str(
        getattr(settings, "DOMAIN_AUTH_HEADER", "REMOTE_USER") or "REMOTE_USER"
    )
    details = {
        "enabled": bool(enabled),
        "header": header,
        "auto_create": bool(
            getattr(config, "domain_auth_auto_create", None)
            if getattr(config, "domain_auth_auto_create", None) is not None
            else getattr(settings, "DOMAIN_AUTH_AUTO_CREATE", True)
        ),
        "default_profile": getattr(config, "domain_auth_default_profile", None)
        or str(getattr(settings, "DOMAIN_AUTH_DEFAULT_PROFILE", "pilot_user") or "pilot_user"),
    }
    if not enabled:
        return readiness_check(
            "domain_auth",
            "SSO / Domain auth",
            "ready",
            "Доменная авторизация выключена; обычный login остаётся основным способом входа.",
            action_path="/settings/sso",
            action_label="Открыть SSO",
            details=details,
        )
    if not has_value(header):
        return readiness_check(
            "domain_auth",
            "SSO / Domain auth",
            "error",
            "Доменная авторизация включена, но header пользователя не задан.",
            action_path="/settings/sso",
            action_label="Настроить SSO",
            details=details,
        )
    return readiness_check(
        "domain_auth",
        "SSO / Domain auth",
        "warning",
        "SSO включён. Проверьте, что reverse proxy удаляет входящий spoofed header и сам выставляет trusted header.",
        action_path="/settings/sso",
        action_label="Проверить SSO",
        details=details,
    )


def ldap_status_check() -> dict[str, Any]:
    enabled = bool(getattr(settings, "LDAP_ENABLED", False))
    backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", []) or [])
    backend_loaded = any("django_auth_ldap" in str(item) for item in backends)
    server_uri = str(getattr(settings, "LDAP_SERVER", "") or getattr(settings, "AUTH_LDAP_SERVER_URI", "") or "")
    search_base = str(getattr(settings, "LDAP_SEARCH_BASE", "") or "")
    bind_dn = str(getattr(settings, "LDAP_BIND_DN", "") or getattr(settings, "AUTH_LDAP_BIND_DN", "") or "")
    bind_password_set = bool(
        str(getattr(settings, "LDAP_BIND_PASSWORD", "") or getattr(settings, "AUTH_LDAP_BIND_PASSWORD", "") or "")
    )
    missing = []
    if enabled and not server_uri:
        missing.append("LDAP_SERVER")
    if enabled and not search_base:
        missing.append("LDAP_SEARCH_BASE")
    if enabled and bind_dn and not bind_password_set:
        missing.append("LDAP_BIND_PASSWORD")
    details = {
        "enabled": enabled,
        "backend_loaded": backend_loaded,
        "server_configured": bool(server_uri),
        "search_base_configured": bool(search_base),
        "bind_dn_configured": bool(bind_dn),
        "bind_password_configured": bind_password_set,
        "start_tls": bool(getattr(settings, "LDAP_START_TLS", False)),
        "ignore_cert": bool(getattr(settings, "LDAP_IGNORE_CERT", False)),
        "ca_cert_configured": bool(
            getattr(settings, "LDAP_CA_CERT_FILE", "") or getattr(settings, "LDAP_CA_CERT_DIR", "")
        ),
        "missing": missing,
    }
    if not enabled:
        return readiness_check(
            "ldap_login",
            "LDAP Login",
            "ready",
            "LDAP login выключен; это env/startup настройка и она показана read-only на SSO странице.",
            action_path="/settings/sso",
            action_label="Открыть SSO",
            details=details,
        )
    if missing or not backend_loaded:
        return readiness_check(
            "ldap_login",
            "LDAP Login",
            "error",
            "LDAP_ENABLED=true, но backend или обязательные env значения не готовы.",
            action_path="/settings/sso",
            action_label="Проверить LDAP",
            details=details,
        )
    return readiness_check(
        "ldap_login",
        "LDAP Login",
        "ready",
        "LDAP backend загружен, обязательные env значения заданы.",
        action_path="/settings/sso",
        action_label="Открыть SSO",
        details=details,
    )


def plugin_marketplace_check() -> dict[str, Any]:
    from plugin_marketplace.checks import plugin_marketplace_deploy_check

    errors = plugin_marketplace_deploy_check(None)
    details = {
        "debug": bool(settings.DEBUG),
        "issues": [{"id": item.id, "message": str(item.msg), "hint": str(item.hint or "")} for item in errors],
    }
    if errors:
        first = errors[0]
        return readiness_check(
            "plugin_marketplace",
            "Plugin Marketplace",
            "error",
            f"{first.id}: {first.msg}",
            action_path="/settings/plugins",
            action_label="Открыть плагины",
            details=details,
        )
    if settings.DEBUG:
        return readiness_check(
            "plugin_marketplace",
            "Plugin Marketplace",
            "warning",
            "Marketplace deploy-checks чистые, но DEBUG=true ослабляет production hardening.",
            action_path="/settings/plugins",
            action_label="Открыть плагины",
            details=details,
        )
    return readiness_check(
        "plugin_marketplace",
        "Plugin Marketplace",
        "ready",
        "Marketplace deploy-checks не нашли ошибок production-конфигурации.",
        action_path="/settings/plugins",
        action_label="Открыть плагины",
        details=details,
    )
