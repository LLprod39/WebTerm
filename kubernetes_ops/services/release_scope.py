from __future__ import annotations

from typing import Any

from django.conf import settings

PRODUCTION_ENVIRONMENTS = {"prod", "production"}
PRODUCTION_CORE_EVIDENCE_REFS = (
    ("production_approval", "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "<change-or-approval-id>"),
    (
        "production_evidence",
        "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF",
        "<operator-reviewed production evidence bundle ref>",
    ),
    (
        "identity_runtime",
        "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF",
        "<production SSO/Keycloak runtime evidence ref>",
    ),
    (
        "live_provider",
        "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF",
        "<production Rancher/Fleet/Devtron live provider evidence ref>",
    ),
    ("readonly_rbac", "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF", "<production read-only RBAC can-i evidence ref>"),
    (
        "kubernetes_mcp",
        "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF",
        "<production Kubernetes MCP READ_ONLY smoke evidence ref>",
    ),
    (
        "production_rollback",
        "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF",
        "<production rollback drill evidence ref>",
    ),
    (
        "native_verification",
        "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF",
        "<production native verification evidence ref>",
    ),
)
LOCAL_EVIDENCE_MARKERS = (
    "127.0.0.1",
    "localhost",
    "host.docker.internal",
    "kind-",
    "minikube",
    "k3d-",
    "local-",
    "fixture-",
    "demo-",
    "-demo",
    ".demo.",
    "demo.",
    ".webterm.local",
    "webterm-k8s-demo",
    "mcp-demo",
    "demo-mcp",
    ".example.test",
    "example.invalid",
)


def build_kubernetes_release_scope_report(
    *,
    provider_probes: list[dict[str, Any]],
    sync_dry_run: list[dict[str, Any]],
    readonly_rbac_live: dict[str, Any],
    studio_mcp: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_environment = _release_environment()
    approval_ref = _production_approval_ref()
    production_target = target_environment in PRODUCTION_ENVIRONMENTS
    indicators = _scope_indicators(
        provider_probes=provider_probes,
        sync_dry_run=sync_dry_run,
        readonly_rbac_live=readonly_rbac_live,
        studio_mcp=studio_mcp or {},
    )
    local_indicators = [item for item in indicators if item.get("classification") == "local"]
    reference_checks = production_core_reference_checks(production_required=production_target)
    missing_refs = [item for item in reference_checks if item["required"] and not item["present"]]
    missing_non_approval_refs = [item for item in missing_refs if item["id"] != "production_approval"]

    if not production_target:
        status = "local" if local_indicators else "pilot"
        reason = "production target environment is not selected"
    elif not approval_ref:
        status = "missing_approval"
        reason = "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF is required for production release evidence"
    elif local_indicators:
        status = "local_evidence"
        reason = "local/test evidence cannot approve production sidebar enablement"
    elif missing_non_approval_refs:
        status = "missing_refs"
        reason = "production evidence refs are required: " + ", ".join(
            item["setting"] for item in missing_non_approval_refs
        )
    else:
        status = "ready"
        reason = "production release scope is explicitly approved"

    return {
        "success": status == "ready",
        "status": status,
        "target_environment": target_environment,
        "production_target": production_target,
        "approval_ref_present": bool(approval_ref),
        "approval_ref": approval_ref,
        "core_evidence_ready": not missing_refs,
        "missing_reference_count": len(missing_refs),
        "missing_required_references": missing_refs,
        "required_references": reference_checks,
        "local_indicator_count": len(local_indicators),
        "local_indicators": local_indicators,
        "indicators": indicators,
        "reason": reason,
    }


def _release_environment() -> str:
    value = str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()
    return value or "local"


def _production_approval_ref() -> str:
    return str(getattr(settings, "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "") or "").strip()


def production_core_reference_checks(*, production_required: bool | None = None) -> list[dict[str, Any]]:
    required = (
        _release_environment() in PRODUCTION_ENVIRONMENTS if production_required is None else bool(production_required)
    )
    return [
        _reference_item(ref_id, setting, expected, required)
        for ref_id, setting, expected in PRODUCTION_CORE_EVIDENCE_REFS
    ]


def _reference_item(ref_id: str, setting: str, expected: str, required: bool) -> dict[str, Any]:
    value = str(getattr(settings, setting, "") or "").strip()
    return {
        "id": ref_id,
        "setting": setting,
        "expected": expected,
        "required": bool(required),
        "present": bool(value),
    }


def _scope_indicators(
    *,
    provider_probes: list[dict[str, Any]],
    sync_dry_run: list[dict[str, Any]],
    readonly_rbac_live: dict[str, Any],
    studio_mcp: dict[str, Any],
) -> list[dict[str, str]]:
    indicators: list[dict[str, str]] = []
    context = str(readonly_rbac_live.get("context") or "").strip()
    if context:
        indicators.append(_indicator("readonly_rbac_live.context", context))
    service_account = str(readonly_rbac_live.get("service_account") or "").strip()
    if service_account:
        indicators.append(_indicator("readonly_rbac_live.service_account", service_account))

    mcp_server = studio_mcp.get("mcp_server") if isinstance(studio_mcp.get("mcp_server"), dict) else {}
    mcp_name = str(mcp_server.get("name") or "").strip()
    if mcp_name:
        indicators.append(_indicator("studio_mcp.name", mcp_name))
    mcp_url = str(mcp_server.get("url") or "").strip()
    if mcp_url:
        indicators.append(_indicator("studio_mcp.url", mcp_url))
    mcp_transport = str(mcp_server.get("transport") or "").strip()
    if mcp_transport:
        indicators.append(_indicator("studio_mcp.transport", mcp_transport))

    for item in provider_probes:
        provider_name = str(item.get("provider_name") or "").strip()
        if provider_name:
            indicators.append(_indicator("provider_probe.provider_name", provider_name))
        provider_base_url = str(item.get("provider_base_url") or "").strip()
        if provider_base_url:
            indicators.append(_indicator("provider_probe.provider_base_url", provider_base_url))
        path = str(item.get("path") or "").strip()
        if path:
            indicators.append(_indicator("provider_probe.path", path))

    for item in sync_dry_run:
        provider_name = str(item.get("provider_name") or "").strip()
        if provider_name:
            indicators.append(_indicator("sync_dry_run.provider_name", provider_name))
        provider_kind = str(item.get("provider_kind") or "").strip()
        if provider_kind:
            indicators.append(_indicator("sync_dry_run.provider_kind", provider_kind))

    return indicators


def _indicator(source: str, value: str) -> dict[str, str]:
    return {
        "source": source,
        "value": value,
        "classification": "local" if is_local_release_indicator(value) else "external",
    }


def is_local_release_indicator(value: str) -> bool:
    lowered = value.strip().lower()
    return any(marker in lowered for marker in LOCAL_EVIDENCE_MARKERS)
