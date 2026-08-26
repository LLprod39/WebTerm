from __future__ import annotations

from typing import Any

from web_ui.services.settings_readiness_common import SEVERITY_RANK
from web_ui.services.settings_readiness_config import (
    ai_provider_check,
    deployment_mode_check,
    domain_auth_check,
    ldap_status_check,
    managed_secret_check,
    notification_check,
    placeholder_secret_check,
    plugin_marketplace_check,
    runtime_config_paths_check,
)
from web_ui.services.settings_readiness_runtime import (
    access_policy_check,
    ansible_runtime_check,
    runtime_limits_check,
    server_secret_storage_check,
    workers_check,
)


def build_settings_readiness_report() -> dict[str, Any]:
    checks = [
        deployment_mode_check(),
        placeholder_secret_check(),
        managed_secret_check(),
        runtime_config_paths_check(),
        ai_provider_check(),
        notification_check(),
        domain_auth_check(),
        ldap_status_check(),
        server_secret_storage_check(),
        access_policy_check(),
        runtime_limits_check(),
        workers_check(),
        ansible_runtime_check(),
        plugin_marketplace_check(),
    ]
    summary = {
        "ready": sum(1 for item in checks if item["severity"] == "ready"),
        "warning": sum(1 for item in checks if item["severity"] == "warning"),
        "error": sum(1 for item in checks if item["severity"] == "error"),
        "total": len(checks),
    }
    worst = max(checks, key=lambda item: SEVERITY_RANK.get(item["severity"], 0))["severity"]
    return {"success": True, "status": worst, "summary": summary, "checks": checks}
