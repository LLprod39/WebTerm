from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import (
    K8sAppRef,
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.permissions import kubernetes_permission_check, kubernetes_permission_policy
from kubernetes_ops.services.access_model import build_kubernetes_access_model_report, kubernetes_access_model_check
from kubernetes_ops.services.admin_action_review_readiness import (
    build_admin_action_post_review_report,
    kubernetes_admin_action_post_review_check,
)
from kubernetes_ops.services.admin_interactive_transport_readiness import (
    build_admin_interactive_transport_report,
    kubernetes_admin_interactive_transport_check,
)
from kubernetes_ops.services.admin_recording_readiness import (
    build_admin_recording_retention_report,
    kubernetes_admin_recording_retention_check,
)
from kubernetes_ops.services.freshness import sync_freshness
from kubernetes_ops.services.frontend_e2e import kubernetes_frontend_e2e_check
from kubernetes_ops.services.identity_runtime import (
    build_kubernetes_identity_runtime_report,
    kubernetes_identity_runtime_check,
)
from kubernetes_ops.services.operator_docs import build_kubernetes_operator_docs_report, kubernetes_operator_docs_check
from kubernetes_ops.services.release_artifact import build_kubernetes_release_evidence_artifact_report
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS, is_local_release_indicator, production_core_reference_checks
from kubernetes_ops.services.security_review import build_kubernetes_security_review, kubernetes_security_review_check
from kubernetes_ops.services.terminal_safety import (
    build_kubernetes_terminal_safety_report,
    kubernetes_terminal_safety_check,
)
from kubernetes_ops.studio_integration import (
    STUDIO_FEATURE_MCP,
    STUDIO_FEATURE_PIPELINES,
    kubernetes_safety_skill_ready,
    owned_kubernetes_mcp_server,
    user_has_studio_feature,
)
from servers.models import BackgroundWorkerState
from servers.worker_state import serialize_background_worker_state


def _check(check_id: str, status: str, detail: str, *, required: bool = True) -> dict[str, Any]:
    return {"id": check_id, "status": status, "detail": detail, "required": required}


def _provider_check(kind: str, label: str) -> dict[str, Any]:
    count = K8sProvider.objects.filter(kind=kind, enabled=True).count()
    if count:
        return _check(f"{kind}_provider", "ready", f"{label} provider configured: {count}")
    return _check(f"{kind}_provider", "missing", f"{label} provider is not configured")


def _sync_worker_check(worker_state: dict[str, Any]) -> dict[str, Any]:
    status = str(worker_state.get("status") or "missing")
    last_cycle = worker_state.get("last_cycle_finished_at") or worker_state.get("heartbeat_at") or "never"
    interval = int(getattr(settings, "KUBERNETES_OPS_SYNC_INTERVAL_SECONDS", 300) or 300)
    command = f"python manage.py run_kubernetes_ops_sync_worker --daemon --interval {interval}"
    if status == "running" and not worker_state.get("is_stale"):
        return _check("sync_worker", "ready", f"Kubernetes sync worker is running. Last heartbeat/cycle: {last_cycle}.")
    if worker_state.get("is_stale") and status != "missing":
        return _check("sync_worker", "missing", f"Kubernetes sync worker lease is stale. Last heartbeat/cycle: {last_cycle}.")
    return _check(
        "sync_worker",
        "missing",
        f"Kubernetes periodic sync worker is not running. Start `{command}` or `docker compose --env-file .env.production -f docker-compose.production.yml up -d kubernetes-ops-sync`.",
    )


def _sync_worker_state() -> dict[str, Any]:
    states = BackgroundWorkerState.objects.filter(worker_kind=KUBERNETES_OPS_SYNC_WORKER).order_by("-heartbeat_at", "worker_key")
    fallback: dict[str, Any] | None = None
    for state in states:
        serialized = serialize_background_worker_state(KUBERNETES_OPS_SYNC_WORKER, worker_key=state.worker_key)
        if serialized.get("status") == BackgroundWorkerState.STATUS_RUNNING and not serialized.get("is_stale"):
            return serialized
        if fallback is None:
            fallback = serialized
    return fallback or serialize_background_worker_state(KUBERNETES_OPS_SYNC_WORKER)


def _provider_health_check() -> dict[str, Any]:
    providers = list(K8sProvider.objects.filter(enabled=True).order_by("kind", "name"))
    if not providers:
        return _check("provider_health", "missing", "No enabled Kubernetes providers are configured.")

    unhealthy: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    for provider in providers:
        freshness = sync_freshness(provider.last_sync_at, last_error=provider.last_error, enabled=provider.enabled)
        status = str(freshness["sync_status"])
        label = f"{provider.kind}:{provider.name}"
        if status == "error":
            unhealthy.append(label)
        elif status == "stale":
            stale.append(label)
        elif status == "missing":
            missing.append(label)

    if unhealthy:
        return _check("provider_health", "missing", "Provider sync errors: " + ", ".join(unhealthy) + ".")
    if stale:
        return _check("provider_health", "missing", "Provider sync data is stale: " + ", ".join(stale) + ".")
    if missing:
        return _check("provider_health", "missing", "Providers have not completed a successful sync: " + ", ".join(missing) + ".")
    return _check("provider_health", "ready", f"Enabled providers have fresh sync metadata: {len(providers)}.")


def _sidebar_release_scope_check(user=None) -> dict[str, Any]:
    gate = _sidebar_release_gate_report(user)
    target_environment = str(gate["target_environment"])
    approval_ref = str(gate["approval_ref"])
    local_indicators = gate["local_indicators"]
    missing_refs = [item for item in gate["missing_required_references"] if item["id"] != "production_approval"]
    if not gate["production_target"]:
        return _check(
            "sidebar_release_scope",
            "missing",
            f"Sidebar is locked because KUBERNETES_OPS_RELEASE_ENVIRONMENT={target_environment or 'local'} is not production.",
        )
    if not approval_ref:
        return _check(
            "sidebar_release_scope",
            "missing",
            "Sidebar is locked until KUBERNETES_OPS_PRODUCTION_APPROVAL_REF is set.",
        )
    if local_indicators:
        preview = ", ".join(f"{item['source']}={item['value']}" for item in local_indicators[:4])
        return _check(
            "sidebar_release_scope",
            "missing",
            f"Sidebar is locked because configured Kubernetes evidence still contains local markers: {preview}.",
        )
    if missing_refs:
        settings_list = ", ".join(str(item["setting"]) for item in missing_refs)
        return _check(
            "sidebar_release_scope",
            "missing",
            f"Sidebar is locked until production evidence refs are set: {settings_list}.",
        )
    return _check("sidebar_release_scope", "ready", f"Production sidebar release scope approved by {approval_ref}.")


def _sidebar_release_gate_report(user=None) -> dict[str, Any]:
    target_environment = str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()
    approval_ref = str(getattr(settings, "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "") or "").strip()
    local_indicators = _configured_local_release_indicators(user)
    production_target = target_environment in PRODUCTION_ENVIRONMENTS
    references = production_core_reference_checks(production_required=production_target)
    missing_refs = [item for item in references if item["required"] and not item["present"]]
    return {
        "target_environment": target_environment,
        "production_target": production_target,
        "approval_ref_present": bool(approval_ref),
        "approval_ref": approval_ref,
        "core_evidence_ready": not missing_refs,
        "missing_reference_count": len(missing_refs),
        "missing_required_references": missing_refs,
        "required_references": references,
        "local_indicator_count": len(local_indicators),
        "local_indicators": local_indicators,
        "ready": production_target and bool(approval_ref) and not local_indicators and not missing_refs,
    }


def _release_evidence_artifact_check(*, require_ready: bool) -> dict[str, Any]:
    report = build_kubernetes_release_evidence_artifact_report(require_ready=require_ready)
    return _check("release_evidence_artifact", str(report["status"]), str(report["detail"]), required=require_ready)


def _configured_local_release_indicators(user=None) -> list[dict[str, str]]:
    indicators: list[dict[str, str]] = []
    for provider in K8sProvider.objects.filter(enabled=True).order_by("kind", "name"):
        _append_local_indicator(indicators, "provider.name", provider.name)
        _append_local_indicator(indicators, "provider.base_url", provider.base_url)
    for cluster in K8sCluster.objects.order_by("name"):
        _append_local_indicator(indicators, "cluster.name", cluster.name)
        labels = cluster.labels if isinstance(cluster.labels, dict) else {}
        for key in ("kube_context", "context", "cluster_context", "rancher_cluster_id"):
            _append_local_indicator(indicators, f"cluster.labels.{key}", str(labels.get(key) or ""))
    mcp_server = owned_kubernetes_mcp_server(user) if user is not None else None
    if mcp_server is not None:
        _append_local_indicator(indicators, "studio_mcp.name", getattr(mcp_server, "name", ""))
        _append_local_indicator(indicators, "studio_mcp.url", getattr(mcp_server, "url", ""))
    return indicators


def _append_local_indicator(indicators: list[dict[str, str]], source: str, value: str) -> None:
    normalized = str(value or "").strip()
    if normalized and is_local_release_indicator(normalized):
        indicators.append({"source": source, "value": _public_local_indicator_value(source, normalized)})


def _public_local_indicator_value(source: str, value: str) -> str:
    if "url" in source or "base_url" in source:
        return "[local-url]"
    return value[:120]


def _studio_automation_check(user) -> dict[str, Any]:
    if not user or not getattr(user, "is_authenticated", False):
        return _check("studio_automation", "manual", "Studio automation readiness needs an authenticated operator context.", required=False)

    missing: list[str] = []
    if not user_has_studio_feature(user, STUDIO_FEATURE_PIPELINES):
        missing.append("Studio pipelines access")
    if not user_has_studio_feature(user, STUDIO_FEATURE_MCP):
        missing.append("Studio MCP access")
    if not kubernetes_safety_skill_ready():
        missing.append("kubernetes-safety skill")

    mcp_server = owned_kubernetes_mcp_server(user)
    if mcp_server is None:
        missing.append("owned Kubernetes MCP server")

    if missing:
        return _check(
            "studio_automation",
            "missing",
            "Studio diagnosis draft is not launch-ready: " + ", ".join(missing) + ".",
            required=False,
        )
    if mcp_server.last_test_ok is False:
        return _check(
            "studio_automation",
            "missing",
            f"Kubernetes MCP server `{mcp_server.name}` exists but its last connection test failed.",
            required=False,
        )
    if mcp_server.last_test_ok is None:
        return _check(
            "studio_automation",
            "manual",
            f"Kubernetes MCP server `{mcp_server.name}` exists but has not been connection-tested yet.",
            required=False,
        )
    return _check(
        "studio_automation",
        "ready",
        f"Studio diagnosis draft can bind owned Kubernetes MCP `{mcp_server.name}` with kubernetes-safety.",
        required=False,
    )


def build_kubernetes_readiness_report(user=None, *, include_release_artifact_gate: bool = True) -> dict[str, Any]:
    cluster_count = K8sCluster.objects.count()
    namespace_count = K8sNamespace.objects.count()
    workload_count = K8sWorkloadRef.objects.count()
    pod_count = K8sPodRef.objects.count()
    network_count = K8sNetworkRef.objects.count()
    event_count = K8sEvent.objects.count()
    app_count = K8sAppRef.objects.count()
    fleet_count = K8sFleetBundle.objects.count()
    worker_state = _sync_worker_state()
    override = str(getattr(settings, "KUBERNETES_OPS_READY_FOR_SIDEBAR", "") or "").lower() in {"1", "true", "yes"}
    checks = [
        _check(
            "architecture_guard",
            "ready",
            "Repository guard is checked by scripts/check_architecture_sizes.py --strict-new outside request path.",
        ),
        kubernetes_permission_check(user),
        kubernetes_access_model_check(),
        kubernetes_identity_runtime_check(),
        _provider_check(K8sProvider.KIND_RANCHER, "Rancher"),
        _provider_check(K8sProvider.KIND_DEVTRON, "Devtron"),
        _provider_health_check(),
        _check(
            "read_only_sync",
            "ready" if cluster_count or namespace_count or workload_count or pod_count or network_count or event_count or app_count or fleet_count else "missing",
            f"Normalized inventory rows: clusters={cluster_count}, namespaces={namespace_count}, workloads={workload_count}, pods={pod_count}, network_refs={network_count}, events={event_count}, apps={app_count}, fleet_bundles={fleet_count}",
        ),
        _sync_worker_check(worker_state),
        _studio_automation_check(user),
        kubernetes_security_review_check(),
        kubernetes_terminal_safety_check(user),
        kubernetes_admin_action_post_review_check(),
        kubernetes_admin_interactive_transport_check(),
        kubernetes_admin_recording_retention_check(),
        kubernetes_operator_docs_check(),
        kubernetes_frontend_e2e_check(),
        _sidebar_release_scope_check(user),
    ]
    if include_release_artifact_gate:
        checks.append(_release_evidence_artifact_check(require_ready=override))
    required_ok = all(item["status"] == "ready" for item in checks if item["required"])
    ready_for_sidebar = required_ok and override
    summary = {
        "ready": sum(1 for item in checks if item["status"] == "ready"),
        "missing": sum(1 for item in checks if item["status"] == "missing"),
        "manual": sum(1 for item in checks if item["status"] == "manual"),
        "total": len(checks),
    }
    status = "ready" if ready_for_sidebar else ("configured" if required_ok else "not_configured")
    return {
        "success": True,
        "status": status,
        "ready_for_sidebar": ready_for_sidebar,
        "summary": summary,
        "access_policy": kubernetes_permission_policy(user),
        "security_review": build_kubernetes_security_review(),
        "terminal_safety": build_kubernetes_terminal_safety_report(user),
        "admin_action_post_review": build_admin_action_post_review_report(),
        "admin_interactive_transport": build_admin_interactive_transport_report(),
        "admin_recording_retention": build_admin_recording_retention_report(),
        "operator_docs": build_kubernetes_operator_docs_report(),
        "access_model": build_kubernetes_access_model_report(),
        "identity_runtime": build_kubernetes_identity_runtime_report(),
        "production_gate": _sidebar_release_gate_report(user),
        "checks": checks,
        "worker_state": worker_state,
    }
