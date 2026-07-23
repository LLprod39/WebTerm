from __future__ import annotations

from typing import Any

from django.utils import timezone

from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sCluster,
    K8sEvent,
    K8sWorkloadRef,
)
from kubernetes_ops.services.action_sanitizers import reference_action_text, sanitize_action_value
from kubernetes_ops.services.action_verification_targets import (
    _admin_action_for_request,
    _cluster_for_target,
    _cluster_fresh_after,
    _fresh_after,
    _parse_time,
    _pods_for_target,
    _resource_evidence,
    _resource_row_for_target,
    _workload_evidence,
    _workload_for_target,
)


def build_native_action_verification_plan(
    *, action_request: K8sActionRequest, execution: dict[str, Any], created_at=None
) -> dict[str, Any]:
    now = created_at or timezone.now()
    target = _safe_target(action_request=action_request, execution=execution)
    checks = _checks_for_action(action_request.action, target=target, execution=execution)
    return {
        "status": "pending",
        "required": True,
        "mode": "native_post_action",
        "created_at": now.isoformat(),
        "action": action_request.action,
        "operation": reference_action_text(execution.get("operation") or ""),
        "target": target,
        "checks": checks,
        "check_ids": [item["id"] for item in checks],
        "payload_stored": False,
        "sensitive_values_stored": False,
    }


def mark_native_verification_plan_recorded(
    *, report: dict[str, Any], verified: bool, recorded_at=None, checks: Any = None
) -> dict[str, Any]:
    plan = report.get("verification_plan") if isinstance(report.get("verification_plan"), dict) else {}
    if not plan or plan.get("mode") != "native_post_action":
        return {}
    now = recorded_at or timezone.now()
    status = "verified" if verified else "failed"
    planned_checks = plan.get("checks") if isinstance(plan.get("checks"), list) else []
    return {
        **plan,
        "status": status,
        "recorded_at": now.isoformat(),
        "recorded_check_count": len(checks) if isinstance(checks, list) else 0,
        "checks": [
            {
                **item,
                "status": "recorded" if verified else "needs_review",
            }
            for item in planned_checks
            if isinstance(item, dict)
        ],
    }


def evaluate_native_action_verification_plan(*, action_request: K8sActionRequest, evaluated_at=None) -> dict[str, Any]:
    now = evaluated_at or timezone.now()
    report = action_request.report if isinstance(action_request.report, dict) else {}
    plan = report.get("verification_plan") if isinstance(report.get("verification_plan"), dict) else {}
    if action_request.status != K8sActionRequest.STATUS_EXECUTED_NATIVE:
        return _evaluation("skipped", now, reason="action_request_not_executed_native")
    if plan.get("mode") != "native_post_action" or plan.get("status") not in {"pending", "needs_review"}:
        return _evaluation("skipped", now, reason="verification_plan_not_pending")

    target = plan.get("target") if isinstance(plan.get("target"), dict) else {}
    cluster = _cluster_for_target(action_request, target)
    executed_at = _parse_time(report.get("executed_at") or plan.get("created_at"))
    planned_checks = plan.get("checks") if isinstance(plan.get("checks"), list) else []
    checks = [
        _evaluate_check(check, action_request=action_request, cluster=cluster, target=target, executed_at=executed_at)
        for check in planned_checks
        if isinstance(check, dict)
    ]
    verified = bool(checks) and all(check.get("status") == "passed" for check in checks)
    return _evaluation(
        "verified" if verified else "needs_review",
        now,
        verified=verified,
        checks=checks,
        check_count=len(checks),
        payload_stored=False,
        sensitive_values_stored=False,
    )


def record_native_action_verification_evaluation(
    *, action_request: K8sActionRequest, evaluated_by: str = "", evaluated_at=None
) -> K8sActionRequest:
    evaluation = evaluate_native_action_verification_plan(action_request=action_request, evaluated_at=evaluated_at)
    if evaluation.get("status") == "skipped":
        return action_request

    report = action_request.report if isinstance(action_request.report, dict) else {}
    plan = report.get("verification_plan") if isinstance(report.get("verification_plan"), dict) else {}
    merged_checks = _merge_evaluated_checks(plan.get("checks"), evaluation.get("checks"))
    verified = bool(evaluation.get("verified"))
    if verified:
        action_request.status = K8sActionRequest.STATUS_VERIFIED_NATIVE
    checked_plan = {
        **plan,
        "status": evaluation["status"],
        "auto_evaluated": True,
        "evaluated_at": evaluation["evaluated_at"],
        "evaluated_by": reference_action_text(evaluated_by or "webterm-native-verifier"),
        "checks": merged_checks,
        "check_ids": [item.get("id") for item in merged_checks if item.get("id")],
        "payload_stored": False,
        "sensitive_values_stored": False,
    }
    action_request.report = {
        **report,
        "status": action_request.status,
        "verified": verified,
        "verification_mode": "native_post_action_auto",
        "native_execution_performed_by_webterm": True,
        "external_execution": False,
        "requires_verification": not verified,
        "auto_verification": sanitize_action_value(evaluation),
        "verification_plan": checked_plan,
    }
    action_request.execution_policy = {
        **(action_request.execution_policy if isinstance(action_request.execution_policy, dict) else {}),
        "native_verification_auto_evaluated": True,
        "native_verification_auto_recorded": verified,
        "verification_auto_evaluated_at": evaluation["evaluated_at"],
    }
    action_request.save(update_fields=["status", "report", "execution_policy", "updated_at"])
    return action_request


def run_pending_native_action_verifications(
    *, limit: int = 50, evaluated_by: str = "webterm-native-verifier"
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 50), 200))
    candidates = (
        K8sActionRequest.objects.select_related("cluster")
        .filter(status=K8sActionRequest.STATUS_EXECUTED_NATIVE, report__verification_plan__mode="native_post_action")
        .order_by("updated_at", "id")[:limit]
    )
    verified = needs_review = skipped = 0
    request_ids: list[str] = []
    for action_request in candidates:
        before = action_request.status
        updated = record_native_action_verification_evaluation(action_request=action_request, evaluated_by=evaluated_by)
        request_ids.append(str(updated.request_id))
        plan_status = ((updated.report or {}).get("verification_plan") or {}).get("status")
        if updated.status == K8sActionRequest.STATUS_VERIFIED_NATIVE and before != updated.status:
            verified += 1
        elif plan_status == "needs_review":
            needs_review += 1
        else:
            skipped += 1
    return {
        "success": True,
        "mode": "native_post_action_auto",
        "processed": len(request_ids),
        "verified": verified,
        "needs_review": needs_review,
        "skipped": skipped,
        "request_ids": request_ids,
        "payload_stored": False,
        "sensitive_values_stored": False,
    }


def _safe_target(*, action_request: K8sActionRequest, execution: dict[str, Any]) -> dict[str, Any]:
    raw_target = execution.get("target") if isinstance(execution.get("target"), dict) else action_request.target or {}
    target = sanitize_action_value(raw_target)
    return {
        "cluster_id": reference_action_text(target.get("cluster_id") or ""),
        "cluster_name": reference_action_text(target.get("cluster_name") or ""),
        "api_version": reference_action_text(target.get("api_version") or ""),
        "kind": reference_action_text(target.get("kind") or ""),
        "resource": reference_action_text(target.get("resource") or ""),
        "namespace": reference_action_text(target.get("namespace") or ""),
        "name": reference_action_text(target.get("name") or ""),
        "replicas": target.get("replicas") if isinstance(target.get("replicas"), int) else execution.get("replicas"),
        "dry_run_action_id": reference_action_text(
            ((execution.get("dry_run_proof") or {}).get("id")) or target.get("dry_run_action_id") or ""
        ),
        "manifest_fingerprint_present": bool(target.get("manifest_fingerprint")),
    }


def _evaluation(status: str, evaluated_at, **extra: Any) -> dict[str, Any]:
    return {"status": status, "evaluated_at": evaluated_at.isoformat(), **extra}


def _evaluate_check(
    check: dict[str, Any],
    *,
    action_request: K8sActionRequest,
    cluster: K8sCluster | None,
    target: dict[str, Any],
    executed_at,
) -> dict[str, Any]:
    check_id = str(check.get("id") or "")
    if cluster is None:
        return _check_result(check_id, "missing", "cluster_not_found")
    if check_id in {"apply_action_completed", "patch_action_completed"}:
        return _admin_action_completed(check_id, action_request)
    if check_id in {"rollout_status_observed", "workload_readiness_observed"}:
        return _workload_ready(check_id, cluster=cluster, target=target, executed_at=executed_at)
    if check_id == "pod_readiness_observed":
        return _pods_ready(check_id, cluster=cluster, target=target, executed_at=executed_at)
    if check_id == "desired_replicas_observed":
        return _desired_replicas(check_id, cluster=cluster, target=target, executed_at=executed_at)
    if check_id == "resource_generation_observed":
        return _resource_present(check_id, cluster=cluster, target=target, executed_at=executed_at)
    if check_id == "resource_absence_observed":
        return _resource_absent(check_id, cluster=cluster, target=target, executed_at=executed_at)
    if check_id == "dependent_health_checked":
        return _dependent_health(check_id, cluster=cluster, target=target, executed_at=executed_at)
    if check_id == "recent_warning_events_checked":
        return _recent_warning_events(check_id, cluster=cluster, target=target, executed_at=executed_at)
    return _check_result(check_id, "needs_review", "unsupported_check")


def _admin_action_completed(check_id: str, action_request: K8sActionRequest) -> dict[str, Any]:
    admin_action = _admin_action_for_request(action_request)
    if admin_action is None:
        return _check_result(check_id, "missing", "admin_action_not_found")
    passed = admin_action.status == K8sAdminAction.STATUS_COMPLETED
    return _check_result(
        check_id,
        "passed" if passed else "needs_review",
        "admin_action_completed" if passed else "admin_action_not_completed",
        evidence={
            "admin_action_id": str(admin_action.action_id),
            "admin_action_status": admin_action.status,
            "verb": admin_action.verb,
        },
    )


def _workload_ready(check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at) -> dict[str, Any]:
    workload = _workload_for_target(cluster, target)
    if workload is None:
        return _check_result(check_id, "missing", "workload_not_found")
    evidence = _workload_evidence(workload)
    if not _fresh_after(workload.last_sync_at, executed_at):
        return _check_result(check_id, "missing", "workload_sync_not_fresh", evidence=evidence)
    passed = (
        workload.ready >= workload.desired
        and workload.desired > 0
        and workload.health not in {K8sCluster.HEALTH_DEGRADED, K8sCluster.HEALTH_UNKNOWN}
    )
    return _check_result(
        check_id,
        "passed" if passed else "needs_review",
        "workload_ready" if passed else "workload_not_ready",
        evidence=evidence,
    )


def _desired_replicas(check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at) -> dict[str, Any]:
    workload = _workload_for_target(cluster, target)
    if workload is None:
        return _check_result(check_id, "missing", "workload_not_found")
    evidence = _workload_evidence(workload)
    if not _fresh_after(workload.last_sync_at, executed_at):
        return _check_result(check_id, "missing", "workload_sync_not_fresh", evidence=evidence)
    expected = target.get("replicas")
    passed = isinstance(expected, int) and workload.desired == expected
    return _check_result(
        check_id,
        "passed" if passed else "needs_review",
        "desired_replicas_matched" if passed else "desired_replicas_mismatch",
        evidence={**evidence, "expected_replicas": expected},
    )


def _pods_ready(check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at) -> dict[str, Any]:
    pods = list(_pods_for_target(cluster, target))
    if not pods:
        return _check_result(check_id, "missing", "pods_not_found")
    stale = [pod.name for pod in pods if not _fresh_after(pod.last_sync_at, executed_at)]
    if stale:
        return _check_result(
            check_id, "missing", "pod_sync_not_fresh", evidence={"pod_count": len(pods), "stale_count": len(stale)}
        )
    unhealthy = [
        pod.name
        for pod in pods
        if pod.total_containers <= 0
        or pod.ready_containers < pod.total_containers
        or pod.health in {K8sCluster.HEALTH_DEGRADED, K8sCluster.HEALTH_UNKNOWN}
        or (pod.phase and pod.phase not in {"Running", "Succeeded"})
    ]
    return _check_result(
        check_id,
        "passed" if not unhealthy else "needs_review",
        "pods_ready" if not unhealthy else "pods_not_ready",
        evidence={"pod_count": len(pods), "unhealthy_count": len(unhealthy)},
    )


def _resource_present(check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at) -> dict[str, Any]:
    row = _resource_row_for_target(cluster, target)
    if row is None:
        return _check_result(check_id, "missing", "resource_not_found")
    evidence = _resource_evidence(row)
    if not _fresh_after(getattr(row, "last_sync_at", None), executed_at):
        return _check_result(check_id, "missing", "resource_sync_not_fresh", evidence=evidence)
    return _check_result(check_id, "passed", "resource_observed", evidence=evidence)


def _resource_absent(check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at) -> dict[str, Any]:
    if not _cluster_fresh_after(cluster, executed_at):
        return _check_result(check_id, "missing", "cluster_sync_not_fresh")
    row = _resource_row_for_target(cluster, target)
    return _check_result(
        check_id,
        "passed" if row is None else "needs_review",
        "resource_absent" if row is None else "resource_still_present",
        evidence={"resource_present": row is not None},
    )


def _dependent_health(check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at) -> dict[str, Any]:
    if not _cluster_fresh_after(cluster, executed_at):
        return _check_result(check_id, "missing", "cluster_sync_not_fresh")
    namespace = str(target.get("namespace") or "")
    workloads = (
        K8sWorkloadRef.objects.filter(cluster=cluster, namespace=namespace)
        if namespace
        else K8sWorkloadRef.objects.filter(cluster=cluster)
    )
    degraded = workloads.filter(health__in=[K8sCluster.HEALTH_DEGRADED, K8sCluster.HEALTH_UNKNOWN]).count()
    return _check_result(
        check_id,
        "passed" if degraded == 0 else "needs_review",
        "dependent_health_ok" if degraded == 0 else "dependent_health_degraded",
        evidence={"checked_workloads": workloads.count(), "degraded_workloads": degraded},
    )


def _recent_warning_events(
    check_id: str, *, cluster: K8sCluster, target: dict[str, Any], executed_at
) -> dict[str, Any]:
    if not _cluster_fresh_after(cluster, executed_at):
        return _check_result(check_id, "missing", "event_sync_not_fresh")
    events = K8sEvent.objects.filter(cluster=cluster, severity__in=[K8sEvent.SEVERITY_WARNING, K8sEvent.SEVERITY_ERROR])
    namespace = str(target.get("namespace") or "")
    name = str(target.get("name") or target.get("resource") or "")
    if namespace:
        events = events.filter(namespace=namespace)
    if name:
        events = events.filter(involved_name=name)
    if executed_at is not None:
        events = events.filter(last_seen_at__gte=executed_at)
    count = events.count()
    return _check_result(
        check_id,
        "passed" if count == 0 else "needs_review",
        "no_recent_warning_events" if count == 0 else "recent_warning_events_found",
        evidence={"warning_event_count": count},
    )


def _check_result(check_id: str, status: str, reason: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": reference_action_text(check_id, limit=120),
        "status": status,
        "reason": reference_action_text(reason, limit=200),
        "evidence": sanitize_action_value(evidence or {}),
        "payload_stored": False,
        "sensitive_values_stored": False,
    }


def _merge_evaluated_checks(planned: Any, evaluated: Any) -> list[dict[str, Any]]:
    evaluated_by_id = (
        {item.get("id"): item for item in evaluated if isinstance(item, dict)} if isinstance(evaluated, list) else {}
    )
    rows = []
    for item in planned if isinstance(planned, list) else []:
        if not isinstance(item, dict):
            continue
        rows.append({**item, **(evaluated_by_id.get(item.get("id")) or {})})
    return rows


def _checks_for_action(action: str, *, target: dict[str, Any], execution: dict[str, Any]) -> list[dict[str, Any]]:
    if action == K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART:
        return [
            _check("rollout_status_observed", "Confirm the rollout completed for the target workload."),
            _check("pod_readiness_observed", "Confirm target Pods are ready after restart."),
            _check("recent_warning_events_checked", "Check recent Events for warnings after restart."),
        ]
    if action == K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE:
        return [
            _check(
                "desired_replicas_observed",
                "Confirm the workload desired replica count matches the approved request.",
                expected=target.get("replicas"),
            ),
            _check("workload_readiness_observed", "Confirm workload readiness after scaling."),
            _check("recent_warning_events_checked", "Check recent Events for warnings after scaling."),
        ]
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_APPLY:
        return [
            _check(
                "apply_action_completed",
                "Confirm server-side apply completed through the linked Admin action.",
                expected=execution.get("admin_action_status") or (execution.get("action") or {}).get("status"),
            ),
            _check("resource_generation_observed", "Confirm the applied resource generation or revision is visible."),
            _check("recent_warning_events_checked", "Check recent Events for warnings after apply."),
        ]
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_PATCH:
        return [
            _check(
                "patch_action_completed",
                "Confirm the patch completed through the linked Admin action.",
                expected=execution.get("admin_action_status") or (execution.get("action") or {}).get("status"),
            ),
            _check("resource_generation_observed", "Confirm the patched resource generation or revision is visible."),
            _check("recent_warning_events_checked", "Check recent Events for warnings after patch."),
        ]
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_DELETE:
        return [
            _check("resource_absence_observed", "Confirm the deleted resource is no longer returned by the API."),
            _check("dependent_health_checked", "Confirm owner or dependent workload health is acceptable."),
            _check("recent_warning_events_checked", "Check recent Events for warnings after delete."),
        ]
    return [_check("post_action_evidence_recorded", "Record post-action evidence for this native execution.")]


def _check(check_id: str, description: str, *, expected: Any = "") -> dict[str, Any]:
    payload = {
        "id": check_id,
        "status": "pending",
        "required": True,
        "description": description,
        "evidence_type": "read_only_post_action",
    }
    if expected not in ("", None):
        payload["expected"] = sanitize_action_value(expected)
    return payload
