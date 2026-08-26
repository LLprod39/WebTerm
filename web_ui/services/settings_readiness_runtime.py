from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from app.background_workers import STUDIO_WORKER_SPECS
from app.runtime_limit_config import runtime_limits_payload
from app.worker_state import serialize_background_worker_kind_state
from core_ui.managed_secrets import (
    MCP_ENV_NAMESPACE,
    NOTIFICATION_SECRET_NAMESPACE,
    SERVER_AUTH_NAMESPACE,
    SERVER_SUDO_NAMESPACE,
)
from core_ui.models import ManagedSecret
from servers.models import BackgroundWorkerState, Server
from servers.playbooks.dispatch import PLAYBOOK_EXECUTION_WORKER_KIND
from servers.services.ansible_engine import detect_ansible
from servers.services.ansible_validator_client import validator_runtime_available, validator_socket_path
from web_ui.services.settings_readiness_common import readiness_check


def ansible_runtime_check() -> dict[str, Any]:
    """Report validation and execution readiness without changing either runtime."""

    socket_path = validator_socket_path()
    if socket_path:
        try:
            validation_available = validator_runtime_available()
        except Exception:
            validation_available = False
        runtime = {
            "method": "isolated-worker" if validation_available else "none",
            "version": "image-managed",
            "image": str(getattr(settings, "WEBTERM_ANSIBLE_IMAGE", "webterm-ansible:latest")),
        }
    else:
        detected = detect_ansible()
        validation_available = bool(detected.get("available"))
        runtime = {
            "method": str(detected.get("method") or "none"),
            "version": str(detected.get("version") or ""),
            "binary": str(detected.get("binary") or ""),
        }

    worker_ready = BackgroundWorkerState.objects.filter(
        worker_kind=PLAYBOOK_EXECUTION_WORKER_KIND,
        status=BackgroundWorkerState.STATUS_RUNNING,
        lease_expires_at__gt=timezone.now(),
    ).exists()
    details = {
        **runtime,
        "validation_available": validation_available,
        "execution_worker_ready": worker_ready,
    }
    if validation_available and worker_ready:
        return readiness_check(
            "ansible_runtime",
            "Ansible",
            "ready",
            "Проверка YAML и сервис запуска Ansible готовы.",
            action_path="/automation",
            action_label="Открыть Ansible",
            details=details,
        )
    if validation_available:
        return readiness_check(
            "ansible_runtime",
            "Ansible",
            "warning",
            "Проверка YAML доступна, но сервис запуска не передаёт свежий heartbeat.",
            action_path="/automation",
            action_label="Открыть Ansible",
            details=details,
        )
    return readiness_check(
        "ansible_runtime",
        "Ansible",
        "warning",
        "Валидатор Ansible недоступен; проекты можно редактировать, но проверка и запуск заблокированы.",
        action_path="/automation",
        action_label="Открыть Ansible",
        details=details,
    )


def server_secret_storage_check() -> dict[str, Any]:
    legacy_password_count = Server.objects.exclude(encrypted_password="").count()
    legacy_sudo_count = Server.objects.exclude(encrypted_sudo_password="").count()
    details = {
        "legacy_server_password_count": legacy_password_count,
        "legacy_server_sudo_password_count": legacy_sudo_count,
        "managed_server_password_count": ManagedSecret.objects.filter(namespace=SERVER_AUTH_NAMESPACE).count(),
        "managed_server_sudo_password_count": ManagedSecret.objects.filter(namespace=SERVER_SUDO_NAMESPACE).count(),
        "managed_mcp_secret_count": ManagedSecret.objects.filter(namespace=MCP_ENV_NAMESPACE).count(),
        "managed_notification_secret_count": ManagedSecret.objects.filter(
            namespace=NOTIFICATION_SECRET_NAMESPACE
        ).count(),
    }
    if legacy_password_count + legacy_sudo_count:
        return readiness_check(
            "server_secret_storage",
            "Server secret storage",
            "error",
            "Legacy server-секреты ещё не перенесены. Запустите migrate_legacy_server_secrets --apply --clear-legacy.",
            details=details,
        )
    return readiness_check(
        "server_secret_storage",
        "Server secret storage",
        "ready",
        "Legacy server secrets не найдены; текущие секреты хранятся только через ManagedSecret.",
        details=details,
    )


def access_policy_check() -> dict[str, Any]:
    active_staff_count = User.objects.filter(is_active=True, is_staff=True).count()
    active_user_count = User.objects.filter(is_active=True).count()
    details = {"active_staff_count": active_staff_count, "active_user_count": active_user_count}
    if active_staff_count == 0:
        return readiness_check(
            "access_policy",
            "Администраторы",
            "error",
            "Нет активного staff-пользователя. После запуска некому будет управлять настройками и доступами.",
            action_path="/settings/users",
            action_label="Открыть пользователей",
            details=details,
        )
    return readiness_check(
        "access_policy",
        "Администраторы",
        "ready",
        f"Найдено активных staff-пользователей: {active_staff_count}.",
        action_path="/settings/users",
        action_label="Открыть пользователей",
        details=details,
    )


def workers_check() -> dict[str, Any]:
    channel_backend = settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
    celery_broker = str(getattr(settings, "CELERY_BROKER_URL", "") or "")
    celery_backend = str(getattr(settings, "CELERY_RESULT_BACKEND", "") or "")
    worker_states = []
    not_ready = []
    for worker_name, spec in STUDIO_WORKER_SPECS.items():
        state = serialize_background_worker_kind_state(spec["worker_kind"])
        ready = state["status"] == "running" and not state["is_stale"]
        worker_states.append(
            {
                "worker": worker_name,
                "worker_kind": spec["worker_kind"],
                "command": spec["command"],
                "ready": ready,
                "state": state,
            }
        )
        if not ready:
            not_ready.append(worker_name)

    details = {
        "channel_backend": channel_backend,
        "celery_broker_configured": bool(celery_broker),
        "celery_result_backend_configured": bool(celery_backend),
        "workers": worker_states,
    }
    if not settings.DEBUG and channel_backend == "channels.layers.InMemoryChannelLayer":
        return readiness_check(
            "runtime_workers",
            "Runtime workers",
            "error",
            "Channels использует InMemoryChannelLayer при DEBUG=false. Нужен Redis channel layer.",
            details=details,
        )
    if not celery_broker or not celery_backend:
        return readiness_check(
            "runtime_workers",
            "Runtime workers",
            "warning",
            "Celery broker/result backend не настроены явно. Background jobs могут работать не так, как ожидается.",
            details=details,
        )
    if not_ready:
        return readiness_check(
            "runtime_workers",
            "Runtime workers",
            "warning",
            "Не все Studio workers имеют свежий heartbeat: " + ", ".join(not_ready) + ".",
            details=details,
        )
    return readiness_check(
        "runtime_workers",
        "Runtime workers",
        "ready",
        "Redis/Celery settings заданы, Studio workers имеют свежий heartbeat.",
        details=details,
    )


def runtime_limits_check() -> dict[str, Any]:
    payload = runtime_limits_payload()
    values = payload["values"]
    sources = payload["sources"]
    disabled = [
        key
        for key in (
            "agent_active_runs_per_user_limit",
            "agent_active_runs_global_limit",
            "pipeline_active_runs_per_user_limit",
            "pipeline_active_runs_global_limit",
            "ssh_terminal_sessions_per_user_limit",
            "ssh_terminal_sessions_global_limit",
        )
        if int(values.get(key) or 0) <= 0
    ]
    llm_budget_enabled = int(values.get("llm_daily_token_limit_per_user") or 0) > 0
    web_overrides = [key for key, source in sources.items() if source == "web"]
    details = {
        "values": values,
        "sources": sources,
        "web_override_count": len(web_overrides),
        "disabled_limits": disabled,
        "llm_budget_enabled": llm_budget_enabled,
    }
    if disabled:
        return readiness_check(
            "runtime_limits",
            "Runtime limits",
            "warning",
            "Некоторые active-run/session лимиты выключены. Для пилота лучше иметь мягкие ограничения.",
            action_path="/settings/limits",
            action_label="Открыть лимиты",
            details=details,
        )
    if not llm_budget_enabled:
        return readiness_check(
            "runtime_limits",
            "Runtime limits",
            "warning",
            "Run/session лимиты включены, но дневной LLM budget на пользователя отключен.",
            action_path="/settings/limits",
            action_label="Открыть лимиты",
            details=details,
        )
    return readiness_check(
        "runtime_limits",
        "Runtime limits",
        "ready",
        "Operational soft limits и дневной LLM budget заданы.",
        action_path="/settings/limits",
        action_label="Открыть лимиты",
        details=details,
    )
