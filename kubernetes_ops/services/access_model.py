from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from kubernetes_ops.services.readonly_rbac import (
    READONLY_SERVICE_ACCOUNT_CONTRACT,
    build_kubernetes_readonly_rbac_report,
)

ACCESS_MODEL_DOC_MARKERS = {
    "report": (
        "docs/WebTerm_Kubernetes_Ops_Rancher_Fleet_Devtron_Report.md",
        (
            "# 7. SSO, RBAC и модель доступа",
            "## 7.3. Проверяемый MVP access model",
            "Keycloak group -> WebTerm feature -> Rancher/Devtron role",
            "render_kubernetes_ops_readonly_rbac",
        ),
    ),
    "runbook": (
        "docs/architecture/KUBERNETES_OPS_OPERATIONS.md",
        (
            "### OIDC/RBAC Access Model",
            "webterm-kubernetes-readers",
            "webterm-kubernetes-admins",
            "webterm-studio-kubernetes-operators",
            "render_kubernetes_ops_readonly_rbac",
        ),
    ),
}

ACCESS_ROLE_MAPPING: tuple[dict[str, Any], ...] = (
    {
        "keycloak_group": "webterm-kubernetes-readers",
        "webterm_feature": "kubernetes",
        "webterm_role": "Kubernetes reader",
        "rancher_role": "project/cluster read-only",
        "devtron_role": "application view + logs",
        "allowed_webterm_capabilities": ["overview", "inventory.read", "events.read", "pod.logs.snapshot", "actions.request_approval"],
        "denied_webterm_capabilities": ["providers.write", "rollout_restart.native", "pod.exec", "apply_yaml", "delete"],
    },
    {
        "keycloak_group": "webterm-kubernetes-admins",
        "webterm_feature": "kubernetes + staff",
        "webterm_role": "Kubernetes provider admin",
        "rancher_role": "cluster/project admin outside WebTerm",
        "devtron_role": "environment admin outside WebTerm",
        "allowed_webterm_capabilities": ["providers.write", "providers.sync", "providers.probe", "actions.verify_external"],
        "denied_webterm_capabilities": ["rollout_restart.native", "pod.exec", "cluster_terminal", "node_debug"],
    },
    {
        "keycloak_group": "webterm-studio-kubernetes-operators",
        "webterm_feature": "kubernetes + studio_pipelines + studio_mcp",
        "webterm_role": "Read-only Studio diagnosis operator",
        "rancher_role": "read-only evidence source",
        "devtron_role": "read-only app evidence source",
        "allowed_webterm_capabilities": ["actions.diagnose", "mcp.kubernetes_describe_workload.read_only"],
        "denied_webterm_capabilities": ["mcp.rollout_restart", "mcp.apply_yaml", "mcp.exec"],
    },
)

READ_ONLY_SERVICE_ACCOUNT = READONLY_SERVICE_ACCOUNT_CONTRACT


def build_kubernetes_access_model_report(*, base_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(base_dir if base_dir is not None else settings.BASE_DIR)
    missing_markers = _missing_doc_markers(root)
    role_errors = _role_mapping_errors()
    service_account_errors = _service_account_errors()
    rbac_report = build_kubernetes_readonly_rbac_report()
    rbac_errors = rbac_report.get("validation", {}).get("errors", [])
    status = "ready" if not missing_markers and not role_errors and not service_account_errors and not rbac_errors else "missing"
    return {
        "status": status,
        "identity_provider": "Keycloak/OIDC",
        "source_of_truth": {
            "webterm": "feature flag and staff status for WebTerm UI/API capabilities",
            "rancher": "cluster/project RBAC and Fleet platform ownership",
            "devtron": "application/environment permissions and deployment history",
        },
        "docs": {name: {"path": path, "required_markers": list(markers)} for name, (path, markers) in ACCESS_MODEL_DOC_MARKERS.items()},
        "missing_markers": missing_markers,
        "role_mapping_errors": role_errors,
        "service_account_errors": service_account_errors,
        "rbac_manifest_errors": rbac_errors,
        "role_mappings": [dict(item) for item in ACCESS_ROLE_MAPPING],
        "read_only_service_account": dict(READ_ONLY_SERVICE_ACCOUNT),
        "read_only_rbac_manifest": rbac_report,
        "native_mutations_enabled": False,
        "exec_enabled": False,
        "production_gate": "OIDC/RBAC mapping must be documented before multi-user pilot; native mutations remain disabled.",
    }


def kubernetes_access_model_check() -> dict[str, Any]:
    report = build_kubernetes_access_model_report()
    if report["status"] == "ready":
        return {
            "id": "access_model",
            "status": "ready",
            "detail": "OIDC/RBAC role mapping and read-only service account contract are documented and fail-closed.",
            "required": True,
        }
    missing = report["missing_markers"] or report["role_mapping_errors"] or report["service_account_errors"] or report["rbac_manifest_errors"]
    return {
        "id": "access_model",
        "status": "missing",
        "detail": "Kubernetes OIDC/RBAC access model is incomplete: " + ", ".join(str(item) for item in missing),
        "required": True,
    }


def _missing_doc_markers(root: Path) -> list[str]:
    missing: list[str] = []
    for _, (relative_path, markers) in ACCESS_MODEL_DOC_MARKERS.items():
        path = root / relative_path
        content = path.read_text(encoding="utf-8") if path.exists() and path.is_file() else ""
        if not content:
            missing.append(relative_path)
            continue
        missing.extend(f"{relative_path}:{marker}" for marker in markers if marker not in content)
    return missing


def _role_mapping_errors() -> list[str]:
    errors: list[str] = []
    seen_groups: set[str] = set()
    for row in ACCESS_ROLE_MAPPING:
        group = str(row.get("keycloak_group") or "").strip()
        if not group:
            errors.append("missing keycloak_group")
        elif group in seen_groups:
            errors.append(f"duplicate keycloak_group:{group}")
        seen_groups.add(group)
        for field in ("webterm_feature", "webterm_role", "rancher_role", "devtron_role"):
            if not str(row.get(field) or "").strip():
                errors.append(f"{group}:{field}")
        if not row.get("allowed_webterm_capabilities"):
            errors.append(f"{group}:allowed_webterm_capabilities")
        if not row.get("denied_webterm_capabilities"):
            errors.append(f"{group}:denied_webterm_capabilities")
    return errors


def _service_account_errors() -> list[str]:
    errors: list[str] = []
    if READ_ONLY_SERVICE_ACCOUNT.get("allowed_verbs") != ["get", "list", "watch"]:
        errors.append("read_only_service_account:allowed_verbs")
    denied = set(READ_ONLY_SERVICE_ACCOUNT.get("denied_verbs") or [])
    if not {"create", "update", "patch", "delete"}.issubset(denied):
        errors.append("read_only_service_account:denied_write_verbs")
    denied_subresources = set(READ_ONLY_SERVICE_ACCOUNT.get("denied_subresources") or [])
    if not {"pods/exec", "pods/attach", "pods/portforward"}.issubset(denied_subresources):
        errors.append("read_only_service_account:denied_subresources")
    return errors
