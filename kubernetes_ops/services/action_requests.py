from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.utils import timezone

from kubernetes_ops.models import K8sActionRequest, K8sAppRef, K8sCluster, K8sFleetBundle
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_gitops import gitops_merge_request_preview
from kubernetes_ops.services.action_production_templates import rollout_restart_production_template
from kubernetes_ops.services.action_resources import (
    resource_apply_preview,
    resource_delete_preview,
    resource_patch_preview,
)
from kubernetes_ops.services.action_rollback import build_action_rollback_plan
from kubernetes_ops.services.action_sanitizers import (
    MAX_TEXT,
)
from kubernetes_ops.services.action_sanitizers import (
    bounded_action_text as _bounded_text,
)
from kubernetes_ops.services.action_sanitizers import (
    reference_action_text as _reference_text,
)
from kubernetes_ops.services.action_sanitizers import (
    sanitize_action_value as _sanitize_value,
)
from kubernetes_ops.services.action_sanitizers import (
    sanitize_public_links as _sanitize_public_links,
)
from kubernetes_ops.services.action_verification import mark_native_verification_plan_recorded
from kubernetes_ops.services.action_workloads import workload_restart_preview, workload_scale_preview

LIFECYCLE = ["request", "preflight", "diff/preview", "approval", "execute", "verify", "report", "audit"]
TERMINAL_STATUSES = {
    K8sActionRequest.STATUS_EXECUTION_BLOCKED,
    K8sActionRequest.STATUS_EXECUTED_NATIVE,
    K8sActionRequest.STATUS_VERIFIED_EXTERNAL,
    K8sActionRequest.STATUS_VERIFIED_NATIVE,
    K8sActionRequest.STATUS_VERIFICATION_FAILED,
    K8sActionRequest.STATUS_REJECTED,
}
APPROVED_EXECUTION_STATUSES = {K8sActionRequest.STATUS_APPROVED_EXTERNAL}
VERIFYABLE_STATUSES = {K8sActionRequest.STATUS_APPROVED_EXTERNAL, K8sActionRequest.STATUS_EXECUTED_NATIVE}

ACTION_METADATA: dict[str, dict[str, Any]] = {
    K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART: {
        "risk_tier": K8sActionRequest.RISK_HIGH,
        "summary": "Request a rollout restart for one workload after approval and verification.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE: {
        "risk_tier": K8sActionRequest.RISK_HIGH,
        "summary": "Request scaling one workload after approval and verification.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_K8S_RESOURCE_APPLY: {
        "risk_tier": K8sActionRequest.RISK_HIGH,
        "summary": "Request applying one Kubernetes resource after a successful dry-run proof, approval and verification.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_K8S_RESOURCE_PATCH: {
        "risk_tier": K8sActionRequest.RISK_HIGH,
        "summary": "Request patching one Kubernetes resource after approval and verification.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_K8S_RESOURCE_DELETE: {
        "risk_tier": K8sActionRequest.RISK_HIGH,
        "summary": "Request deleting one Kubernetes resource after approval and verification.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_FLEET_ROLLOUT_PAUSE: {
        "risk_tier": K8sActionRequest.RISK_MEDIUM,
        "summary": "Request pausing one Fleet rollout after approval.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME: {
        "risk_tier": K8sActionRequest.RISK_MEDIUM,
        "summary": "Request resuming one Fleet rollout after approval.",
        "native_execution": "disabled",
    },
    K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST: {
        "risk_tier": K8sActionRequest.RISK_LOW,
        "summary": "Request a GitOps merge request instead of a direct cluster mutation.",
        "native_execution": "external_gitops",
    },
    K8sActionRequest.ACTION_DEVTRON_OPEN_ROLLBACK: {
        "risk_tier": K8sActionRequest.RISK_MEDIUM,
        "summary": "Request opening a Devtron rollback flow as an audited deep link.",
        "native_execution": "external_devtron",
    },
}

BLOCKED_ACTIONS = {
    "delete_namespace": "Deleting namespaces through WebTerm is blocked.",
    "delete_helm_release": "Deleting Helm releases through WebTerm is blocked.",
    "helm.delete": "Deleting Helm releases through WebTerm is blocked.",
    "helm_release.delete": "Deleting Helm releases through WebTerm is blocked.",
    "kubectl.apply": "Unrestricted kubectl apply through WebTerm is blocked.",
    "apply_yaml": "Unrestricted YAML apply through WebTerm is blocked.",
    "node_debug": "Node debug through WebTerm is blocked.",
    "port_forward": "Port-forward through WebTerm is blocked.",
    "cluster_admin_shell": "Cluster-admin shell through WebTerm is blocked.",
    "rbac.edit": "Editing Kubernetes RBAC through WebTerm is blocked.",
    "edit_rbac": "Editing Kubernetes RBAC through WebTerm is blocked.",
}


def create_kubernetes_action_request(*, user, data: dict[str, Any]) -> K8sActionRequest:
    action = str(data.get("action") or "").strip()
    target = _target_from_data(data)
    reason = _bounded_text(data.get("reason") or "")
    approval_ref = _reference_text(data.get("approval_ref") or data.get("change_request_url") or "", limit=160)

    if not action:
        raise ActionRequestValidationError("action is required.", code="action_required", payload={"target": target})
    if action in BLOCKED_ACTIONS:
        raise ActionRequestValidationError(
            BLOCKED_ACTIONS[action],
            code="action_blocked",
            payload={"action": action, "target": target},
        )
    if action not in ACTION_METADATA:
        raise ActionRequestValidationError(
            "action is not allowed for Kubernetes Ops controlled actions.",
            code="action_not_allowed",
            payload={"action": action, "target": target},
        )
    if not reason:
        raise ActionRequestValidationError(
            "reason is required for Kubernetes action requests.",
            code="reason_required",
            payload={"action": action, "target": target},
        )

    cluster, normalized_target, preview = _preflight_preview(action=action, target=target, user=user)
    rollback_plan = build_action_rollback_plan(action=action, target=normalized_target, preview=preview)
    preview = {**preview, "rollback_plan": rollback_plan}
    if action == K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART:
        preview["production_rollout_restart_template"] = rollout_restart_production_template(
            target=normalized_target,
            preview=preview,
            rollback_plan=rollback_plan,
        )
    policy = build_execution_policy(action, rollback_plan=rollback_plan)
    metadata = ACTION_METADATA[action]
    return K8sActionRequest.objects.create(
        requested_by=user,
        username_snapshot=getattr(user, "username", ""),
        action=action,
        status=K8sActionRequest.STATUS_PENDING_APPROVAL,
        risk_tier=str(metadata["risk_tier"]),
        cluster=cluster,
        target=normalized_target,
        preview=preview,
        execution_policy=policy,
        reason=reason,
        approval_ref=approval_ref,
    )


def block_kubernetes_action_execution(*, action_request: K8sActionRequest, user) -> K8sActionRequest:
    _ensure_action_request_status(
        action_request,
        allowed=APPROVED_EXECUTION_STATUSES,
        transition="execute",
        code="action_request_not_approved",
    )
    reason = (
        "Native Kubernetes mutating execution is disabled in WebTerm. Use the external Rancher, Fleet, Devtron, "
        "or GitOps approval path until execute/verify/report controls are implemented and tested."
    )
    action_request.status = K8sActionRequest.STATUS_EXECUTION_BLOCKED
    action_request.report = {
        "status": "blocked",
        "blocked_at": timezone.now().isoformat(),
        "blocked_by": getattr(user, "username", ""),
        "blocked_reason": reason,
        "verified": False,
    }
    action_request.save(update_fields=["status", "report", "updated_at"])
    return action_request


def approve_external_action_request(
    *, action_request: K8sActionRequest, user, data: dict[str, Any]
) -> K8sActionRequest:
    _ensure_action_request_status(
        action_request,
        allowed={K8sActionRequest.STATUS_PENDING_APPROVAL},
        transition="approve_external",
        code="action_request_not_pending",
    )
    approval_ref = _reference_text(
        data.get("approval_ref") or data.get("change_request_url") or action_request.approval_ref or "", limit=160
    )
    if not approval_ref:
        raise ActionRequestValidationError(
            "approval_ref is required for external approval.",
            code="approval_ref_required",
            payload={"request_id": str(action_request.request_id)},
        )
    summary = _bounded_text(
        data.get("summary") or data.get("reason") or "Approved for external execution.", limit=MAX_TEXT
    )
    now = timezone.now().isoformat()
    previous_report = action_request.report if isinstance(action_request.report, dict) else {}
    previous_policy = action_request.execution_policy if isinstance(action_request.execution_policy, dict) else {}

    action_request.status = K8sActionRequest.STATUS_APPROVED_EXTERNAL
    action_request.approval_ref = approval_ref
    action_request.report = {
        **previous_report,
        "status": K8sActionRequest.STATUS_APPROVED_EXTERNAL,
        "approved": True,
        "approved_at": now,
        "approved_by": getattr(user, "username", ""),
        "approval_ref": approval_ref,
        "approval_summary": summary,
        "native_execution_performed_by_webterm": False,
    }
    action_request.execution_policy = {
        **previous_policy,
        "native_execution_enabled": False,
        "external_approval_recorded": True,
        "approval_recorded_at": now,
        "approved_execution_mode": previous_policy.get("native_execution_mode", "external"),
    }
    action_request.save(update_fields=["status", "approval_ref", "report", "execution_policy", "updated_at"])
    return action_request


def record_external_action_verification(
    *, action_request: K8sActionRequest, user, data: dict[str, Any]
) -> K8sActionRequest:
    _ensure_action_request_status(
        action_request,
        allowed=VERIFYABLE_STATUSES,
        transition="verify_external",
        code="action_request_not_approved",
    )
    outcome = _bounded_text(data.get("outcome") or data.get("status") or "", limit=40).lower()
    if outcome in {"success", "succeeded", "ok", "verified", "pass", "passed"}:
        verified = True
    elif outcome in {"failed", "failure", "error", "not_verified", "fail"}:
        verified = False
    else:
        raise ActionRequestValidationError(
            "outcome must be one of succeeded/failed.",
            code="verification_outcome_required",
            payload={"outcome": outcome},
        )

    summary = _bounded_text(data.get("summary") or data.get("reason") or "")
    if not summary:
        raise ActionRequestValidationError(
            "summary is required for action verification.",
            code="verification_summary_required",
            payload={"request_id": str(action_request.request_id)},
        )

    external_ref = _reference_text(
        data.get("external_ref") or data.get("change_request_url") or data.get("approval_ref") or "", limit=240
    )
    checks = _sanitize_value(data.get("checks") if isinstance(data.get("checks"), list) else [])
    evidence = _sanitize_value(data.get("evidence") if isinstance(data.get("evidence"), dict) else {})
    now = timezone.now().isoformat()
    previous_report = action_request.report if isinstance(action_request.report, dict) else {}
    previous_policy = action_request.execution_policy if isinstance(action_request.execution_policy, dict) else {}
    native_execution = action_request.status == K8sActionRequest.STATUS_EXECUTED_NATIVE
    verified_status = (
        K8sActionRequest.STATUS_VERIFIED_NATIVE if native_execution else K8sActionRequest.STATUS_VERIFIED_EXTERNAL
    )
    verification_plan = (
        mark_native_verification_plan_recorded(
            report=previous_report, verified=verified, recorded_at=timezone.now(), checks=checks
        )
        if native_execution
        else {}
    )

    action_request.status = verified_status if verified else K8sActionRequest.STATUS_VERIFICATION_FAILED
    action_request.report = {
        **previous_report,
        "status": action_request.status,
        "verified": verified,
        "verification_mode": "native_post_action" if native_execution else "external_execution",
        "external_execution": not native_execution,
        "native_execution_performed_by_webterm": native_execution,
        "verified_at": now,
        "verified_by": getattr(user, "username", ""),
        "summary": summary,
        "external_ref": external_ref,
        "checks": checks,
        "evidence": evidence,
    }
    if verification_plan:
        action_request.report["verification_plan"] = verification_plan
    action_request.execution_policy = {
        **previous_policy,
        "native_execution_enabled": bool(previous_policy.get("native_execution_enabled"))
        if native_execution
        else False,
        "external_verification_recorded": not native_execution,
        "native_verification_recorded": native_execution,
        "verification_recorded_at": now,
    }
    action_request.save(update_fields=["status", "report", "execution_policy", "updated_at"])
    return action_request


def build_execution_policy(action: str, *, rollback_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = ACTION_METADATA.get(action, {})
    return {
        "approval_required": True,
        "dry_run_required": True,
        "verification_required": True,
        "rollback_required": bool(rollback_plan),
        "rollback_mode": (rollback_plan or {}).get("mode", ""),
        "rollback_strategy": (rollback_plan or {}).get("strategy", ""),
        "native_execution_enabled": False,
        "native_execution_mode": metadata.get("native_execution", "disabled"),
        "allowed_execution_modes": ["rancher", "fleet", "devtron", "gitops_merge_request"],
        "lifecycle": list(LIFECYCLE),
        "blocked_reason": (
            "WebTerm currently records the request, preflight, preview, and audit only. Direct cluster mutation "
            "stays disabled until approval, restricted credentials, verification, and rollback evidence are ready."
        ),
    }


def sanitized_action_rejection_payload(error: ActionRequestValidationError) -> dict[str, Any]:
    return _sanitize_value(error.payload)


def _ensure_action_request_status(
    action_request: K8sActionRequest,
    *,
    allowed: set[str],
    transition: str,
    code: str,
) -> None:
    if action_request.status in allowed:
        return
    resolved_code = "action_request_not_pending" if action_request.status in TERMINAL_STATUSES else code
    raise ActionRequestValidationError(
        "action request is not in the required state for this transition.",
        code=resolved_code,
        payload={
            "request_id": str(action_request.request_id),
            "status": action_request.status,
            "transition": transition,
            "terminal": action_request.status in TERMINAL_STATUSES,
            "allowed_statuses": sorted(allowed),
        },
    )


def _target_from_data(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("target") if isinstance(data.get("target"), dict) else {}
    target = _sanitize_value(raw)
    for key in (
        "cluster_id",
        "cluster",
        "api_version",
        "namespace",
        "kind",
        "resource",
        "name",
        "workload_id",
        "app_id",
        "bundle_id",
        "bundle_name",
        "repository",
        "branch",
        "base_branch",
        "source_branch",
        "target_branch",
        "path",
        "title",
        "diff_summary",
        "replicas",
        "dry_run_action_id",
        "patch_type",
        "patch_body",
        "confirmation",
        "propagation_policy",
        "changes",
    ):
        if key in data and data.get(key) not in (None, ""):
            target[key] = _sanitize_value(data.get(key))
    return target


def _preflight_preview(
    action: str, target: dict[str, Any], *, user
) -> tuple[K8sCluster | None, dict[str, Any], dict[str, Any]]:
    if action == K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART:
        return workload_restart_preview(target, summary=ACTION_METADATA[action]["summary"])
    if action == K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE:
        return workload_scale_preview(target, summary=ACTION_METADATA[action]["summary"])
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_APPLY:
        return resource_apply_preview(target, user=user, summary=ACTION_METADATA[action]["summary"])
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_PATCH:
        return resource_patch_preview(target, summary=ACTION_METADATA[action]["summary"])
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_DELETE:
        return resource_delete_preview(target, summary=ACTION_METADATA[action]["summary"])
    if action in {K8sActionRequest.ACTION_FLEET_ROLLOUT_PAUSE, K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME}:
        return _fleet_rollout_preview(action, target)
    if action == K8sActionRequest.ACTION_DEVTRON_OPEN_ROLLBACK:
        return _devtron_rollback_preview(target)
    if action == K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST:
        return gitops_merge_request_preview(
            target=target,
            cluster=_cluster_or_none(str(target.get("cluster_id") or target.get("cluster") or "")),
            summary=ACTION_METADATA[action]["summary"],
        )
    raise ActionRequestValidationError(
        "action is not supported.",
        code="action_not_supported",
        payload={"action": action, "target": target},
    )


def _fleet_rollout_preview(
    action: str, target: dict[str, Any]
) -> tuple[K8sCluster | None, dict[str, Any], dict[str, Any]]:
    bundle = _fleet_bundle_from_target(target)
    bundle_name = _bounded_text(
        target.get("bundle_name") or target.get("name") or (bundle.name if bundle else ""), limit=180
    )
    if not bundle_name:
        raise ActionRequestValidationError(
            "Fleet rollout action requires bundle_name.", code="bundle_required", payload={"target": target}
        )
    normalized = {"bundle_name": bundle_name}
    if bundle:
        normalized["bundle_id"] = f"fleet_{bundle.id}"
    return (
        None,
        normalized,
        {
            "summary": ACTION_METADATA[action]["summary"],
            "blast_radius": "fleet_bundle",
            "inventory_match": bool(bundle),
            "current_status": bundle.status if bundle else "unknown",
            "ready": bundle.ready if bundle else None,
            "desired": bundle.desired if bundle else None,
            "affected": [normalized],
            "expected_verification": [
                "Fleet bundle status",
                "target cluster readiness",
                "GitRepo reconciliation status",
            ],
        },
    )


def _devtron_rollback_preview(target: dict[str, Any]) -> tuple[K8sCluster | None, dict[str, Any], dict[str, Any]]:
    app = _app_from_target(target)
    if app is None:
        raise ActionRequestValidationError(
            "Devtron rollback request requires a known app_id.", code="app_required", payload={"target": target}
        )
    normalized = {
        "app_id": f"app_{app.id}",
        "app_name": app.name,
        "cluster_id": f"cluster_{app.cluster_id}",
        "cluster_name": app.cluster.name,
        "namespace": app.namespace,
        "owner": app.owner,
    }
    return (
        app.cluster,
        normalized,
        {
            "summary": ACTION_METADATA[K8sActionRequest.ACTION_DEVTRON_OPEN_ROLLBACK]["summary"],
            "blast_radius": "single_devtron_app",
            "inventory_match": True,
            "current_health": app.health,
            "version": app.version,
            "links": _sanitize_public_links(app.links or {}),
            "affected": [normalized],
            "expected_verification": ["Devtron deployment history", "application health", "pod readiness"],
        },
    )


def _cluster_or_none(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


def _app_from_target(target: dict[str, Any]) -> K8sAppRef | None:
    app_id = str(target.get("app_id") or "").strip()
    numeric = app_id.removeprefix("app_")
    if numeric.isdigit():
        return K8sAppRef.objects.filter(id=int(numeric)).select_related("cluster").first()
    return None


def _fleet_bundle_from_target(target: dict[str, Any]) -> K8sFleetBundle | None:
    bundle_id = str(target.get("bundle_id") or "").strip()
    numeric = bundle_id.removeprefix("fleet_")
    if numeric.isdigit():
        return K8sFleetBundle.objects.filter(id=int(numeric)).first()
    bundle_name = str(target.get("bundle_name") or target.get("name") or "").strip()
    if bundle_name:
        return K8sFleetBundle.objects.filter(name=bundle_name).first()
    return None
