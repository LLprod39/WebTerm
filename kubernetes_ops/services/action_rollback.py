from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sActionRequest
from kubernetes_ops.services.action_sanitizers import reference_action_text, sanitize_action_value


def build_action_rollback_plan(*, action: str, target: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    safe_target = _safe_target(target)
    plan = {
        "status": "required",
        "mode": "metadata_only",
        "action": action,
        "target": safe_target,
        "steps": [],
        "evidence_required": [],
        "payload_stored": False,
        "sensitive_values_stored": False,
    }
    if action == K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE:
        previous = preview.get("current_replicas")
        plan.update(
            {
                "strategy": "scale_back",
                "previous_replicas": previous if isinstance(previous, int) else None,
                "steps": [
                    "verify current health",
                    "scale workload back to previous_replicas if rollback is required",
                    "verify workload readiness",
                ],
                "evidence_required": ["previous_replicas", "post_rollback_workload_readiness", "recent_warning_events"],
            }
        )
    elif action == K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART:
        plan.update(
            {
                "strategy": "rollout_recovery",
                "steps": [
                    "verify rollout health",
                    "use GitOps/Devtron previous version rollback if restart exposes a bad release",
                    "verify pods are ready",
                ],
                "evidence_required": ["rollout_status", "gitops_or_devtron_rollback_ref_if_used", "pod_readiness"],
            }
        )
    elif action == K8sActionRequest.ACTION_K8S_RESOURCE_APPLY:
        plan.update(
            {
                "strategy": "apply_revert",
                "dry_run_action_id": reference_action_text(target.get("dry_run_action_id") or ""),
                "manifest_fingerprint_present": bool(target.get("manifest_fingerprint")),
                "steps": [
                    "prepare previous manifest or GitOps revert",
                    "run fresh dry-run apply for rollback manifest",
                    "apply rollback only after approval",
                ],
                "evidence_required": [
                    "rollback_source_ref",
                    "rollback_dry_run_action_id",
                    "post_rollback_resource_generation",
                ],
            }
        )
    elif action == K8sActionRequest.ACTION_K8S_RESOURCE_PATCH:
        patch_shape = preview.get("patch_shape") if isinstance(preview.get("patch_shape"), dict) else {}
        plan.update(
            {
                "strategy": "reverse_patch",
                "patch_type": reference_action_text(target.get("patch_type") or ""),
                "patch_shape": sanitize_action_value(patch_shape),
                "steps": [
                    "capture current sanitized resource state",
                    "prepare reverse patch or GitOps revert",
                    "dry-run and approve rollback patch",
                ],
                "evidence_required": [
                    "previous_resource_snapshot_ref",
                    "reverse_patch_dry_run_ref",
                    "post_rollback_resource_generation",
                ],
            }
        )
    elif action == K8sActionRequest.ACTION_K8S_RESOURCE_DELETE:
        plan.update(
            {
                "strategy": "restore_deleted_resource",
                "steps": [
                    "confirm restore source exists before deletion",
                    "restore via GitOps or approved apply",
                    "verify dependent workload health",
                ],
                "evidence_required": ["restore_source_ref", "rollback_dry_run_action_id", "dependent_health"],
            }
        )
    else:
        plan.update(
            {
                "status": "external",
                "strategy": "external_owner_rollback",
                "steps": ["use the owning platform rollback path", "record external evidence in WebTerm"],
                "evidence_required": ["external_rollback_ref"],
            }
        )
    return plan


def rollback_plan_is_payload_safe(plan: dict[str, Any]) -> bool:
    return not plan.get("payload_stored") and not plan.get("sensitive_values_stored") and "[redacted]" not in str(plan)


def _safe_target(target: dict[str, Any]) -> dict[str, Any]:
    safe = sanitize_action_value(target)
    return {
        "cluster_id": reference_action_text(safe.get("cluster_id") or ""),
        "cluster_name": reference_action_text(safe.get("cluster_name") or ""),
        "api_version": reference_action_text(safe.get("api_version") or ""),
        "kind": reference_action_text(safe.get("kind") or ""),
        "resource": reference_action_text(safe.get("resource") or ""),
        "namespace": reference_action_text(safe.get("namespace") or ""),
        "name": reference_action_text(safe.get("name") or ""),
        "replicas": safe.get("replicas") if isinstance(safe.get("replicas"), int) else None,
    }
