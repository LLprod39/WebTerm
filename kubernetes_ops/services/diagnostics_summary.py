from __future__ import annotations

from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sEvent, K8sNamespace, K8sNetworkRef, K8sPodRef, K8sWorkloadRef
from kubernetes_ops.services.network_detail import build_network_detail, network_for_value
from kubernetes_ops.services.namespace_detail import build_namespace_detail
from kubernetes_ops.services.pod_detail import build_pod_detail, pod_for_value
from kubernetes_ops.services.workload_detail import build_workload_detail, workload_for_value


HEALTH_SEVERITY = {
    K8sCluster.HEALTH_DEGRADED: "critical",
    K8sCluster.HEALTH_WARNING: "warning",
    K8sCluster.HEALTH_UNKNOWN: "unknown",
    K8sCluster.HEALTH_HEALTHY: "ok",
}
DEFAULT_BLOCKED_ACTIONS = ("exec", "port_forward", "delete", "scale", "restart", "patch", "apply_yaml")


def build_diagnostics_summary(
    *,
    scope: str,
    user=None,
    cluster_id: str = "",
    namespace: str = "",
    namespace_id: str = "",
    workload_id: str = "",
    pod_id: str = "",
    network_id: str = "",
) -> tuple[dict[str, Any] | None, str]:
    scope_type = str(scope or "").strip().lower()
    if scope_type == "cluster":
        cluster = _cluster_for_value(cluster_id)
        if cluster is None:
            return None, "cluster_not_found"
        return _cluster_diagnostics_payload(cluster, user=user), ""
    if scope_type == "workload":
        workload = workload_for_value(workload_id)
        if workload is None:
            return None, "workload_not_found"
        detail = build_workload_detail(workload, user=user)
        return _from_detail(scope_type, detail), ""
    if scope_type == "pod":
        pod = pod_for_value(pod_id)
        if pod is None:
            return None, "pod_not_found"
        detail = build_pod_detail(pod, user=user)
        return _from_detail(scope_type, detail), ""
    if scope_type == "namespace":
        cluster = _cluster_for_value(cluster_id)
        if cluster is None:
            return None, "cluster_not_found"
        detail = build_namespace_detail(cluster, namespace_id or namespace, user=user)
        if detail is None:
            return None, "namespace_not_found"
        return _from_detail(scope_type, detail), ""
    if scope_type == "network":
        network = network_for_value(network_id)
        if network is None:
            return None, "network_not_found"
        detail = build_network_detail(network, user=user)
        return _from_detail(scope_type, detail), ""
    return None, "invalid_scope"


def diagnostics_summary_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    signals = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}
    health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
    return {
        "scope_type": str(scope.get("type") or ""),
        "cluster_id": str(scope.get("cluster_id") or ""),
        "cluster_name": str(scope.get("cluster_name") or ""),
        "namespace": str(scope.get("namespace") or ""),
        "target_id": str(scope.get("target_id") or ""),
        "target_name": str(scope.get("target_name") or ""),
        "health": str(health.get("status") or ""),
        "severity": str(health.get("severity") or ""),
        "finding_count": len(payload.get("findings") or []),
        "warning_event_count": int(signals.get("warning_event_count") or 0),
        "restart_count": int(signals.get("restart_count") or 0),
        "unhealthy_pod_count": int(signals.get("unhealthy_pod_count") or 0),
    }


def _from_detail(scope_type: str, detail: dict[str, Any]) -> dict[str, Any]:
    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    policy = detail.get("policy") if isinstance(detail.get("policy"), dict) else {}
    scope = _scope_payload(scope_type, detail, summary)
    owner_context = _owner_context(detail, summary)
    signals = _signals(summary)
    findings = _findings(scope_type, scope=scope, signals=signals, owner_context=owner_context)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "diagnostics_summary",
        "source": "normalized_inventory",
        "scope": scope,
        "health": {
            "status": signals["health"],
            "severity": HEALTH_SEVERITY.get(signals["health"], "unknown"),
        },
        "signals": signals,
        "owner_context": owner_context,
        "findings": findings,
        "safe_next_steps": _safe_next_steps(scope_type, scope=scope, signals=signals, owner_context=owner_context),
        "webterm_endpoints": _webterm_endpoints(scope_type, scope),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "external_ui": "staff_admin_fallback",
            "external_links_included": False,
            "blocked_actions": list(policy.get("blocked_actions") or DEFAULT_BLOCKED_ACTIONS),
            "requestable_actions": _requestable_actions(policy, owner_context=owner_context),
        },
    }


def _cluster_diagnostics_payload(cluster: K8sCluster, *, user=None) -> dict[str, Any]:
    namespaces = list(K8sNamespace.objects.filter(cluster=cluster).only("id", "name", "health"))
    workloads = list(K8sWorkloadRef.objects.filter(cluster=cluster).only("id", "name", "namespace", "kind", "health", "ready", "desired", "owner", "team"))
    pods = list(K8sPodRef.objects.filter(cluster=cluster).only("id", "name", "namespace", "health", "ready_containers", "total_containers", "restart_count"))
    networks = list(K8sNetworkRef.objects.filter(cluster=cluster).only("id", "name", "namespace", "kind", "health"))
    apps = list(K8sAppRef.objects.filter(cluster=cluster).only("id", "name", "owner", "team")[:100])
    events = list(K8sEvent.objects.filter(cluster=cluster).only("id", "severity")[:200])
    summary = {
        "health": cluster.health,
        "ready": cluster.nodes_ready,
        "desired": cluster.nodes_total,
        "nodes_ready": cluster.nodes_ready,
        "nodes_total": cluster.nodes_total,
        "namespace_count": len(namespaces) or cluster.namespace_count,
        "workload_count": len(workloads) or cluster.workload_count,
        "network_count": len(networks),
        "pod_count": len(pods),
        "event_count": len(events),
        "warning_event_count": sum(1 for event in events if event.severity in {K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR}),
        "restart_count": sum(pod.restart_count for pod in pods),
        "ready_containers": sum(pod.ready_containers for pod in pods),
        "total_containers": sum(pod.total_containers for pod in pods),
        "unhealthy_namespace_count": sum(1 for item in namespaces if item.health != K8sCluster.HEALTH_HEALTHY),
        "unhealthy_workload_count": sum(1 for item in workloads if item.health != K8sCluster.HEALTH_HEALTHY),
        "unhealthy_pod_count": sum(1 for item in pods if item.health != K8sCluster.HEALTH_HEALTHY),
        "owners": sorted({item for item in [*(app.owner for app in apps), *(workload.owner for workload in workloads)] if item}),
        "teams": sorted({item for item in [*(app.team for app in apps), *(workload.team for workload in workloads)] if item}),
    }
    scope = {
        "type": "cluster",
        "cluster_id": f"cluster_{cluster.id}",
        "cluster_name": cluster.name,
        "namespace": "",
        "target_id": f"cluster_{cluster.id}",
        "target_name": cluster.name,
        "target_kind": "Cluster",
    }
    owner_context = _owner_context(
        {"owner_apps": [{"owner": app.owner, "team": app.team, "name": app.name} for app in apps]},
        summary,
    )
    signals = _signals(summary)
    findings = _findings("cluster", scope=scope, signals=signals, owner_context=owner_context)
    return {
        "success": True,
        "mode": "read_only",
        "operation": "diagnostics_summary",
        "source": "normalized_inventory",
        "scope": scope,
        "health": {
            "status": signals["health"],
            "severity": HEALTH_SEVERITY.get(signals["health"], "unknown"),
        },
        "signals": signals,
        "owner_context": owner_context,
        "findings": findings,
        "safe_next_steps": _safe_next_steps("cluster", scope=scope, signals=signals, owner_context=owner_context),
        "webterm_endpoints": _webterm_endpoints("cluster", scope),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "external_ui": "staff_admin_fallback",
            "external_links_included": False,
            "blocked_actions": list(DEFAULT_BLOCKED_ACTIONS),
            "requestable_actions": _requestable_actions({}, owner_context=owner_context),
        },
    }


def _scope_payload(scope_type: str, detail: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    cluster = detail.get("cluster") if isinstance(detail.get("cluster"), dict) else {}
    target = _target_payload(scope_type, detail)
    return {
        "type": scope_type,
        "cluster_id": str(cluster.get("id") or ""),
        "cluster_name": str(cluster.get("name") or ""),
        "namespace": str(target.get("namespace") or summary.get("namespace") or ""),
        "target_id": str(target.get("id") or ""),
        "target_name": str(target.get("name") or ""),
        "target_kind": str(target.get("kind") or ""),
    }


def _target_payload(scope_type: str, detail: dict[str, Any]) -> dict[str, Any]:
    key = {"namespace": "namespace", "workload": "workload", "pod": "pod", "network": "network_ref"}.get(scope_type, "")
    value = detail.get(key) if key else {}
    return value if isinstance(value, dict) else {}


def _owner_context(detail: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    owner_apps = [item for item in detail.get("owner_apps") or detail.get("apps") or [] if isinstance(item, dict)]
    owners = set(str(item.get("owner") or "").strip() for item in owner_apps)
    owners.update(str(item).strip() for item in summary.get("owners") or [])
    owners.discard("")
    teams = set(str(item.get("team") or "").strip() for item in owner_apps)
    teams.update(str(item).strip() for item in summary.get("teams") or [])
    teams.discard("")
    owner_names = sorted({str(item.get("name") or "").strip() for item in owner_apps if str(item.get("name") or "").strip()})
    primary_owner = "devtron" if K8sAppRef.OWNER_DEVTRON in owners else "fleet" if K8sAppRef.OWNER_FLEET in owners else sorted(owners)[0] if owners else "unknown"
    return {
        "primary_owner": primary_owner,
        "owners": sorted(owners),
        "teams": sorted(teams),
        "apps": owner_names[:10],
        "change_path": _change_path(primary_owner),
    }


def _signals(summary: dict[str, Any]) -> dict[str, Any]:
    ready = int(summary.get("ready") or summary.get("ready_workloads") or 0)
    desired = int(summary.get("desired") or summary.get("desired_workloads") or 0)
    ready_containers = int(summary.get("ready_containers") or summary.get("related_ready_containers") or 0)
    total_containers = int(summary.get("total_containers") or summary.get("related_total_containers") or 0)
    restart_count = int(summary.get("restart_count") or summary.get("related_restart_count") or 0)
    return {
        "health": str(summary.get("health") or K8sCluster.HEALTH_UNKNOWN),
        "ready": ready,
        "desired": desired,
        "ready_containers": ready_containers,
        "total_containers": total_containers,
        "restart_count": restart_count,
        "event_count": int(summary.get("event_count") or 0),
        "warning_event_count": int(summary.get("warning_event_count") or 0),
        "unhealthy_app_count": int(summary.get("unhealthy_app_count") or 0),
        "unhealthy_namespace_count": int(summary.get("unhealthy_namespace_count") or 0),
        "unhealthy_workload_count": int(summary.get("unhealthy_workload_count") or 0),
        "unhealthy_pod_count": int(summary.get("unhealthy_pod_count") or 0),
        "pod_count": int(summary.get("pod_count") or summary.get("sibling_pod_count") or 0),
        "network_count": int(summary.get("network_count") or 0),
        "namespace_count": int(summary.get("namespace_count") or 0),
        "workload_count": int(summary.get("workload_count") or 0),
        "nodes_ready": int(summary.get("nodes_ready") or 0),
        "nodes_total": int(summary.get("nodes_total") or 0),
    }


def _findings(
    scope_type: str,
    *,
    scope: dict[str, Any],
    signals: dict[str, Any],
    owner_context: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    health = signals["health"]
    if health in {K8sCluster.HEALTH_DEGRADED, K8sCluster.HEALTH_WARNING, K8sCluster.HEALTH_UNKNOWN}:
        findings.append(_finding("target_health", HEALTH_SEVERITY.get(health, "unknown"), f"{scope_type} health is {health}", {"health": health}))
    if signals["desired"] and signals["ready"] < signals["desired"]:
        findings.append(
            _finding(
                "readiness_gap",
                "warning",
                f"ready {signals['ready']} of {signals['desired']}",
                {"ready": signals["ready"], "desired": signals["desired"]},
            )
        )
    if scope_type == "cluster" and signals["nodes_total"] and signals["nodes_ready"] < signals["nodes_total"]:
        findings.append(
            _finding(
                "node_readiness_gap",
                "warning",
                f"nodes ready {signals['nodes_ready']} of {signals['nodes_total']}",
                {"nodes_ready": signals["nodes_ready"], "nodes_total": signals["nodes_total"]},
            )
        )
    if signals["total_containers"] and signals["ready_containers"] < signals["total_containers"]:
        findings.append(
            _finding(
                "container_readiness_gap",
                "warning",
                f"containers ready {signals['ready_containers']} of {signals['total_containers']}",
                {"ready_containers": signals["ready_containers"], "total_containers": signals["total_containers"]},
            )
        )
    if signals["restart_count"] > 0:
        findings.append(_finding("pod_restarts", "warning", "pod restarts observed", {"restart_count": signals["restart_count"]}))
    if signals["warning_event_count"] > 0:
        findings.append(_finding("warning_events", "warning", "warning or error events are present", {"warning_event_count": signals["warning_event_count"]}))
    if signals["unhealthy_namespace_count"] > 0:
        findings.append(_finding("unhealthy_namespaces", "warning", "unhealthy namespaces are present", {"unhealthy_namespace_count": signals["unhealthy_namespace_count"]}))
    if signals["unhealthy_workload_count"] > 0:
        findings.append(_finding("unhealthy_workloads", "warning", "unhealthy workloads are present", {"unhealthy_workload_count": signals["unhealthy_workload_count"]}))
    if signals["unhealthy_pod_count"] > 0:
        findings.append(_finding("unhealthy_pods", "warning", "unhealthy related pods are present", {"unhealthy_pod_count": signals["unhealthy_pod_count"]}))
    if owner_context["primary_owner"] in {K8sAppRef.OWNER_DEVTRON, K8sAppRef.OWNER_FLEET}:
        findings.append(
            _finding(
                f"{owner_context['primary_owner']}_owned",
                "info",
                f"changes should use {owner_context['change_path']}",
                {"change_path": owner_context["change_path"]},
            )
        )
    if not findings:
        findings.append(_finding("no_immediate_issue", "ok", "no obvious issue in normalized inventory", {}))
    return findings


def _finding(finding_id: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"id": finding_id, "severity": severity, "message": message, "evidence": evidence}


def _safe_next_steps(
    scope_type: str,
    *,
    scope: dict[str, Any],
    signals: dict[str, Any],
    owner_context: dict[str, Any],
) -> list[dict[str, Any]]:
    steps = [
        {"id": "open_webterm_detail", "label": "Open WebTerm detail", "mutates_state": False},
        {"id": "check_events", "label": "Review related events", "mutates_state": False},
    ]
    if scope_type == "cluster":
        steps.append({"id": "review_cluster_inventory", "label": "Review cluster namespaces, workloads and nodes", "mutates_state": False})
    if scope_type in {"pod", "workload", "network"} or (scope_type == "namespace" and signals["pod_count"] > 0):
        steps.append({"id": "logs_snapshot", "label": "Open bounded logs snapshot", "mutates_state": False})
    if owner_context["primary_owner"] == K8sAppRef.OWNER_DEVTRON:
        steps.append({"id": "devtron_context", "label": "Review Devtron AppOps context in WebTerm", "mutates_state": False})
    if owner_context["primary_owner"] == K8sAppRef.OWNER_FLEET:
        steps.append({"id": "fleet_context", "label": "Review Fleet rollout context in WebTerm", "mutates_state": False})
    if signals["health"] != K8sCluster.HEALTH_HEALTHY:
        steps.append({"id": "request_approval", "label": "Request approval before any change", "mutates_state": False})
    return steps


def _requestable_actions(policy: dict[str, Any], *, owner_context: dict[str, Any]) -> list[str]:
    actions = {str(item) for item in policy.get("requestable_actions") or [] if str(item)}
    if owner_context["primary_owner"] == K8sAppRef.OWNER_DEVTRON:
        actions.add("devtron.open_rollback")
    if owner_context["primary_owner"] == K8sAppRef.OWNER_FLEET:
        actions.add("gitops.create_merge_request")
    actions.add("diagnosis.create_draft")
    actions.add("approval.request")
    return sorted(actions)


def _webterm_endpoints(scope_type: str, scope: dict[str, Any]) -> dict[str, str]:
    target_id = scope.get("target_id") or ""
    cluster_id = scope.get("cluster_id") or ""
    namespace = scope.get("namespace") or ""
    if scope_type == "workload" and target_id:
        return {"detail": f"/api/kubernetes/workloads/{target_id}/"}
    if scope_type == "pod" and target_id:
        return {"detail": f"/api/kubernetes/pods/{target_id}/", "logs": f"/api/kubernetes/pods/{target_id}/logs/"}
    if scope_type == "namespace" and cluster_id and namespace:
        return {"detail": f"/api/kubernetes/clusters/{cluster_id}/namespaces/{namespace}/"}
    if scope_type == "network" and target_id:
        return {"detail": f"/api/kubernetes/network/{target_id}/"}
    if scope_type == "cluster" and cluster_id:
        return {
            "detail": f"/api/kubernetes/clusters/{cluster_id}/",
            "namespaces": f"/api/kubernetes/clusters/{cluster_id}/namespaces/",
            "workloads": f"/api/kubernetes/clusters/{cluster_id}/workloads/",
            "events": f"/api/kubernetes/clusters/{cluster_id}/events/",
        }
    return {}


def _change_path(owner: str) -> str:
    if owner == K8sAppRef.OWNER_DEVTRON:
        return "devtron_rollback_or_deploy"
    if owner == K8sAppRef.OWNER_FLEET:
        return "fleet_gitops_or_mr"
    return "webterm_approval_required"


def _cluster_for_value(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()
