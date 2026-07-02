from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from kubernetes_ops.models import K8sActionRequest
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_requests import (
    APPROVED_EXECUTION_STATUSES,
    _ensure_action_request_status,
    block_kubernetes_action_execution,
)
from kubernetes_ops.services.action_rollback import build_action_rollback_plan
from kubernetes_ops.services.action_sanitizers import (
    bounded_action_text,
    reference_action_text,
    sanitize_action_value,
)
from kubernetes_ops.services.action_verification import build_native_action_verification_plan
from kubernetes_ops.services.admin_apply import apply_kubernetes_resource
from kubernetes_ops.services.admin_delete import delete_kubernetes_resource
from kubernetes_ops.services.admin_patch import patch_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_workload_actions import restart_kubernetes_workload, scale_kubernetes_workload


def execute_approved_action_request(*, action_request: K8sActionRequest, user, data: dict[str, Any]) -> K8sActionRequest:
    if not bool(getattr(settings, "KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED", False)):
        return block_kubernetes_action_execution(action_request=action_request, user=user)
    _ensure_action_request_status(
        action_request,
        allowed=APPROVED_EXECUTION_STATUSES,
        transition="execute",
        code="action_request_not_approved",
    )
    if action_request.action not in {
        K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
        K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE,
        K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
        K8sActionRequest.ACTION_K8S_RESOURCE_PATCH,
        K8sActionRequest.ACTION_K8S_RESOURCE_DELETE,
    }:
        return block_kubernetes_action_execution(action_request=action_request, user=user)
    policy = kubernetes_permission_policy(user)
    required_policy = _required_policy(action_request.action)
    if not policy.get("can_execute_approved_action") or not policy.get(required_policy):
        raise ActionRequestValidationError(
            "Native action request execution is not allowed for this user or runtime policy.",
            code="native_action_execution_not_allowed",
            payload={"action": action_request.action, "requires": ["kubernetes_admin_write", required_policy]},
        )
    session_id = bounded_action_text(data.get("session_id") or data.get("admin_session_id") or "", limit=80)
    if not session_id:
        raise ActionRequestValidationError(
            "session_id is required for native action request execution.",
            code="admin_session_id_required",
            payload={"action": action_request.action},
        )
    target = action_request.target or {}
    try:
        execution = _execute_workload_action(action_request=action_request, user=user, session_id=session_id, target=target, data=data)
    except AdminResourceError as exc:
        raise ActionRequestValidationError(
            str(exc),
            code=exc.code,
            payload={"action": action_request.action, **sanitize_action_value(exc.payload or {})},
        ) from exc

    executed_at = timezone.now()
    verification_plan = build_native_action_verification_plan(action_request=action_request, execution=execution, created_at=executed_at)
    preview = action_request.preview if isinstance(action_request.preview, dict) else {}
    rollback_plan = preview.get("rollback_plan") if isinstance(preview.get("rollback_plan"), dict) else build_action_rollback_plan(action=action_request.action, target=action_request.target or {}, preview=preview)
    action_request.status = K8sActionRequest.STATUS_EXECUTED_NATIVE
    action_request.execution_policy = {
        **(action_request.execution_policy or {}),
        "native_execution_enabled": True,
        "native_execution_performed_by_webterm": True,
        "native_execution_mode": "admin_write_session",
        "admin_session_id": session_id,
    }
    action_request.report = {
        **(action_request.report or {}),
        "status": K8sActionRequest.STATUS_EXECUTED_NATIVE,
        "executed_at": executed_at.isoformat(),
        "executed_by": getattr(user, "username", ""),
        "approved": True,
        "approval_ref": action_request.approval_ref,
        "native_execution_performed_by_webterm": True,
        "external_execution": False,
        "verified": False,
        "requires_verification": True,
        "operation": execution.get("operation"),
        "dry_run_action_id": reference_action_text(((execution.get("dry_run_proof") or {}).get("id")) or target.get("dry_run_action_id") or ""),
        "dry_run_bypassed": bool((execution.get("policy") or {}).get("dry_run_bypassed")),
        "replicas": execution.get("replicas"),
        "patch_type": execution.get("patch_type"),
        "redacted": bool(execution.get("redacted")),
        "admin_action_id": (execution.get("action") or {}).get("id"),
        "admin_action_status": (execution.get("action") or {}).get("status"),
        "target": sanitize_action_value(execution.get("target") or {}),
        "path": reference_action_text(execution.get("path") or ""),
        "verification_plan": verification_plan,
        "rollback_plan": rollback_plan,
    }
    action_request.save(update_fields=["status", "execution_policy", "report", "updated_at"])
    return action_request


def _execute_workload_action(*, action_request: K8sActionRequest, user, session_id: str, target: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    common = {
        "user": user,
        "session_id": session_id,
        "cluster_id": str(target.get("cluster_id") or ""),
        "api_version": str(target.get("api_version") or "apps/v1"),
        "kind": str(target.get("kind") or ""),
        "namespace": str(target.get("namespace") or ""),
        "name": str(target.get("name") or ""),
        "reason": action_request.reason,
    }
    if action_request.action == K8sActionRequest.ACTION_K8S_RESOURCE_APPLY:
        manifest = data.get("manifest")
        if not isinstance(manifest, dict):
            raise ActionRequestValidationError("manifest is required for native apply execution.", code="manifest_required")
        return apply_kubernetes_resource(
            user=user,
            session_id=session_id,
            cluster_id=str(target.get("cluster_id") or ""),
            dry_run_action_id=str(target.get("dry_run_action_id") or ""),
            reason=action_request.reason,
            manifest=manifest,
            namespace=str(target.get("namespace") or ""),
            resource=str(target.get("resource") or ""),
        )
    if action_request.action == K8sActionRequest.ACTION_K8S_RESOURCE_PATCH:
        return patch_kubernetes_resource(**common, patch_body=target.get("patch_body"), patch_type=str(target.get("patch_type") or "merge"))
    if action_request.action == K8sActionRequest.ACTION_K8S_RESOURCE_DELETE:
        return delete_kubernetes_resource(
            **common,
            confirmation=str(target.get("confirmation") or ""),
            propagation_policy=str(target.get("propagation_policy") or ""),
        )
    if action_request.action == K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE:
        return scale_kubernetes_workload(**common, replicas=target.get("replicas"))
    return restart_kubernetes_workload(**common)


def _required_policy(action: str) -> str:
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_APPLY:
        return "can_apply_yaml"
    if action == K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE:
        return "can_scale"
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_PATCH:
        return "can_patch"
    if action == K8sActionRequest.ACTION_K8S_RESOURCE_DELETE:
        return "can_delete"
    return "can_restart"
