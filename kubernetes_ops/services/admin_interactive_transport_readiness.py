from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.admin_delete import DEFAULT_PROTECTED_NAMESPACES
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.provider_clients import provider_path
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS

RESTRICTED_CREDENTIAL_EVIDENCE_SETTING = "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF"
PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING = "KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF"
PORT_FORWARD_ALLOWED_TARGETS_SETTING = "KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS"
PORT_FORWARD_PROTECTED_NAMESPACES_SETTING = "KUBERNETES_ADMIN_PORT_FORWARD_PROTECTED_NAMESPACES"
PORT_FORWARD_PRODUCTION_MAX_DURATION_SECONDS = 900
EVIDENCE_SETTING = RESTRICTED_CREDENTIAL_EVIDENCE_SETTING
TRANSPORTS = (
    {
        "id": "exec_stream",
        "enabled_settings": ("KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED", "KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED"),
        "recording_setting": "KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED",
    },
    {
        "id": "port_forward_tunnel",
        "enabled_settings": (
            "KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED",
            "KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED",
        ),
        "recording_setting": "KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED",
    },
    {
        "id": "cluster_terminal",
        "enabled_settings": ("KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED",),
        "recording_setting": "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED",
    },
    {
        "id": "node_debug",
        "enabled_settings": ("KUBERNETES_ADMIN_NODE_DEBUG_ENABLED",),
        "recording_setting": "KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED",
    },
)
PROVIDER_CONTRACTS = {
    "cluster_terminal": {
        "label": "cluster_terminal_path_template",
        "required_placeholders": ("cluster_id", "namespace"),
    },
    "node_debug": {
        "label": "node_debug_path_template",
        "required_placeholders": ("cluster_id", "node_name"),
    },
}


def _target_environment() -> str:
    return str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()


def _evidence_ref() -> str:
    return _setting_ref(RESTRICTED_CREDENTIAL_EVIDENCE_SETTING)


def _setting_ref(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _enabled(settings_names: tuple[str, ...]) -> bool:
    return all(bool(getattr(settings, name, False)) for name in settings_names)


def _transport_report(item: dict[str, Any], *, production: bool, evidence_ref_present: bool) -> dict[str, Any]:
    enabled = _enabled(tuple(item["enabled_settings"]))
    recording_enabled = bool(getattr(settings, str(item["recording_setting"]), False))
    blockers: list[str] = []
    if enabled and not recording_enabled:
        blockers.append("recording_gate_required")
    if enabled and production and not evidence_ref_present:
        blockers.append("restricted_credential_evidence_required")
    network_policy = (
        _port_forward_network_policy_report(enabled=enabled, production=production)
        if item["id"] == "port_forward_tunnel"
        else None
    )
    if network_policy is not None:
        blockers.extend(network_policy["blockers"])
    provider_contract = _provider_contract_report(operation=item["id"], enabled=enabled)
    if provider_contract is not None:
        blockers.extend(provider_contract["blockers"])
    report = {
        "id": item["id"],
        "enabled": enabled,
        "enabled_settings": list(item["enabled_settings"]),
        "recording_enabled": recording_enabled,
        "recording_setting": item["recording_setting"],
        "restricted_credential_evidence_required": bool(enabled and production),
        "restricted_credential_evidence_ready": bool(not enabled or not production or evidence_ref_present),
        "blockers": blockers,
    }
    if network_policy is not None:
        report["network_policy"] = network_policy
    if provider_contract is not None:
        report["provider_contract"] = provider_contract
    return report


def _port_forward_network_policy_report(*, enabled: bool, production: bool) -> dict[str, Any]:
    allowlist = _list_setting(PORT_FORWARD_ALLOWED_TARGETS_SETTING)
    wildcard_targets = sorted(item for item in allowlist if "*" in item)
    protected_namespaces = _protected_namespaces()
    missing_default_protection = sorted(DEFAULT_PROTECTED_NAMESPACES - protected_namespaces)
    evidence_ref = _setting_ref(PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING)
    max_duration = _port_forward_max_duration_seconds()
    blockers: list[str] = []
    if enabled:
        if not allowlist:
            blockers.append("target_allowlist_required")
        if wildcard_targets:
            blockers.append("target_wildcard_not_allowed")
        if missing_default_protection:
            blockers.append("protected_namespace_policy_incomplete")
        if production and not evidence_ref:
            blockers.append("network_policy_evidence_required")
        if production and max_duration > PORT_FORWARD_PRODUCTION_MAX_DURATION_SECONDS:
            blockers.append("duration_cap_too_high")
    return {
        "enabled": enabled,
        "allowed_targets_setting": PORT_FORWARD_ALLOWED_TARGETS_SETTING,
        "allowed_target_count": len(allowlist),
        "wildcard_targets_present": bool(wildcard_targets),
        "protected_namespaces_setting": PORT_FORWARD_PROTECTED_NAMESPACES_SETTING,
        "protected_namespace_count": len(protected_namespaces),
        "default_protected_namespaces_covered": not bool(missing_default_protection),
        "network_policy_evidence_setting": PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING,
        "network_policy_evidence_required": bool(enabled and production),
        "network_policy_evidence_present": bool(evidence_ref),
        "max_duration_seconds": max_duration,
        "production_max_duration_seconds": PORT_FORWARD_PRODUCTION_MAX_DURATION_SECONDS,
        "blockers": blockers,
    }


def _list_setting(name: str, *, fallback: str = "") -> set[str]:
    configured = getattr(settings, name, None)
    if configured is None and fallback:
        configured = getattr(settings, fallback, None)
    values = configured if isinstance(configured, (list, tuple, set)) else str(configured or "").split(",")
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _protected_namespaces() -> set[str]:
    configured = _list_setting(
        PORT_FORWARD_PROTECTED_NAMESPACES_SETTING, fallback="KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES"
    )
    return configured or {item.lower() for item in DEFAULT_PROTECTED_NAMESPACES}


def _port_forward_max_duration_seconds() -> int:
    try:
        value = int(
            getattr(
                settings,
                "KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS",
                PORT_FORWARD_PRODUCTION_MAX_DURATION_SECONDS,
            )
            or PORT_FORWARD_PRODUCTION_MAX_DURATION_SECONDS
        )
    except (TypeError, ValueError):
        value = PORT_FORWARD_PRODUCTION_MAX_DURATION_SECONDS
    return max(60, min(value, 3600))


def _provider_contract_report(*, operation: str, enabled: bool) -> dict[str, Any] | None:
    contract = PROVIDER_CONTRACTS.get(operation)
    if contract is None:
        return None
    providers = list(
        K8sProvider.objects.filter(kind=K8sProvider.KIND_RANCHER, enabled=True).only("id", "name", "labels")
    )
    checked: list[dict[str, Any]] = []
    missing_count = 0
    invalid_count = 0
    for provider in providers:
        validation = validate_provider_interactive_transport_contract(provider, operation=operation, raise_error=False)
        checked.append(validation)
        if validation["status"] == "missing":
            missing_count += 1
        elif validation["status"] == "invalid":
            invalid_count += 1
    blockers: list[str] = []
    if enabled:
        if not providers:
            blockers.append("rancher_provider_required")
        if missing_count:
            blockers.append("provider_contract_required")
        if invalid_count:
            blockers.append("provider_contract_invalid")
    return {
        "operation": operation,
        "required": bool(enabled),
        "label": contract["label"],
        "required_placeholders": list(contract["required_placeholders"]),
        "enabled_rancher_provider_count": len(providers),
        "checked_provider_count": len(checked),
        "missing_provider_count": missing_count,
        "invalid_provider_count": invalid_count,
        "providers": checked[:20],
        "blockers": blockers,
    }


def validate_provider_interactive_transport_contract(
    provider: K8sProvider | None,
    *,
    operation: str,
    raise_error: bool = True,
) -> dict[str, Any]:
    contract = PROVIDER_CONTRACTS.get(operation)
    if contract is None:
        return {"operation": operation, "status": "ready", "required": False, "blockers": []}
    label = str(contract["label"])
    required_placeholders = tuple(str(item) for item in contract["required_placeholders"])
    if provider is None or not provider.enabled or provider.kind != K8sProvider.KIND_RANCHER:
        return _provider_contract_result(
            provider=provider,
            operation=operation,
            label=label,
            required_placeholders=required_placeholders,
            status="missing",
            blockers=["rancher_provider_required"],
            raise_error=raise_error,
            code="rancher_provider_required",
        )
    template = provider_path(provider, label, "").strip()
    if not template:
        return _provider_contract_result(
            provider=provider,
            operation=operation,
            label=label,
            required_placeholders=required_placeholders,
            status="missing",
            blockers=["provider_contract_required"],
            raise_error=raise_error,
            code=f"{operation}_transport_template_required",
        )
    missing_placeholders = [name for name in required_placeholders if "{" + name + "}" not in template]
    unsafe_template = _unsafe_provider_template(template)
    if missing_placeholders or unsafe_template:
        blockers = []
        if missing_placeholders:
            blockers.append("provider_contract_missing_placeholders")
        if unsafe_template:
            blockers.append("provider_contract_unsafe_template")
        return _provider_contract_result(
            provider=provider,
            operation=operation,
            label=label,
            required_placeholders=required_placeholders,
            status="invalid",
            blockers=blockers,
            raise_error=raise_error,
            code=f"{operation}_transport_template_invalid",
            missing_placeholders=missing_placeholders,
        )
    return _provider_contract_result(
        provider=provider,
        operation=operation,
        label=label,
        required_placeholders=required_placeholders,
        status="ready",
        blockers=[],
        raise_error=False,
    )


def _unsafe_provider_template(template: str) -> bool:
    value = str(template or "").strip().lower()
    return "://" in value or value.startswith("//") or "?" in value or "#" in value or "@" in value


def _provider_contract_result(
    *,
    provider: K8sProvider | None,
    operation: str,
    label: str,
    required_placeholders: tuple[str, ...],
    status: str,
    blockers: list[str],
    raise_error: bool,
    code: str = "",
    missing_placeholders: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "operation": operation,
        "status": status,
        "provider_id": getattr(provider, "id", None),
        "provider_name": getattr(provider, "name", ""),
        "label": label,
        "required_placeholders": list(required_placeholders),
        "missing_placeholders": list(missing_placeholders or []),
        "blockers": blockers,
    }
    if raise_error and blockers:
        raise AdminResourceError(
            "Interactive transport provider contract is incomplete.",
            code=code or f"{operation}_provider_contract_required",
            status=409,
            payload=payload,
        )
    return payload


def build_admin_interactive_transport_report() -> dict[str, Any]:
    target_environment = _target_environment()
    production = target_environment in PRODUCTION_ENVIRONMENTS
    evidence_ref_present = bool(_evidence_ref())
    transports = [
        _transport_report(item, production=production, evidence_ref_present=evidence_ref_present) for item in TRANSPORTS
    ]
    blockers = [f"{transport['id']}:{blocker}" for transport in transports for blocker in transport["blockers"]]
    enabled_count = sum(1 for transport in transports if transport["enabled"])
    status = "ready" if not blockers else "missing"
    if blockers:
        detail = "Interactive transport prerequisites are incomplete: " + ", ".join(blockers) + "."
    elif enabled_count:
        detail = f"Interactive transport prerequisites are satisfied for {enabled_count} enabled transport(s)."
    else:
        detail = "Interactive production transports are disabled."
    return {
        "status": status,
        "target_environment": target_environment,
        "production_environment": production,
        "evidence_setting": RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
        "port_forward_network_policy_evidence_setting": PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING,
        "restricted_credential_evidence_present": evidence_ref_present,
        "enabled_transport_count": enabled_count,
        "transports": transports,
        "blockers": blockers,
        "detail": detail,
    }


def kubernetes_admin_interactive_transport_check() -> dict[str, Any]:
    report = build_admin_interactive_transport_report()
    return {
        "id": "admin_interactive_transport",
        "status": report["status"],
        "detail": report["detail"],
        "required": False,
    }


def assert_interactive_transport_prerequisites(operation: str) -> None:
    report = build_admin_interactive_transport_report()
    matching = next((item for item in report["transports"] if item["id"] == operation), None)
    blockers = list(matching.get("blockers") or []) if matching else list(report["blockers"])
    if blockers:
        payload = {
            "operation": operation,
            "blockers": blockers,
            "evidence_setting": RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
        }
        if matching and matching.get("provider_contract") is not None:
            payload["provider_contract"] = matching["provider_contract"]
        if matching and matching.get("network_policy") is not None:
            payload["network_policy"] = matching["network_policy"]
        raise AdminResourceError(
            "Interactive transport prerequisites are incomplete.",
            code="interactive_transport_prerequisites_required",
            status=403,
            payload=payload,
        )
