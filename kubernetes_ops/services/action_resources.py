from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from kubernetes_ops.models import K8sAdminAction, K8sCluster
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_sanitizers import bounded_action_text, sanitize_action_value
from kubernetes_ops.services.admin_patch import PATCH_TYPES
from kubernetes_ops.services.admin_delete import PROTECTED_CLUSTER_KINDS, expected_delete_confirmation, protected_delete_namespaces
from kubernetes_ops.services.admin_resources import build_resource_ref, cluster_for_value


def resource_apply_preview(target: dict[str, Any], *, user, summary: str) -> tuple[K8sCluster, dict[str, Any], dict[str, Any]]:
    dry_run_action_id = bounded_action_text(target.get("dry_run_action_id") or "", limit=80)
    if not dry_run_action_id:
        raise ActionRequestValidationError("dry_run_action_id is required for apply requests.", code="dry_run_proof_required")
    try:
        proof = K8sAdminAction.objects.select_related("cluster", "user").get(
            action_id=dry_run_action_id,
            verb=K8sAdminAction.VERB_DRY_RUN_APPLY,
            status=K8sAdminAction.STATUS_DRY_RUN,
        )
    except (K8sAdminAction.DoesNotExist, ValueError, TypeError) as exc:
        raise ActionRequestValidationError("A successful dry-run proof is required for apply requests.", code="dry_run_proof_required") from exc
    if proof.user_id != getattr(user, "id", None):
        raise ActionRequestValidationError("Dry-run proof must belong to the requester.", code="dry_run_proof_owner_mismatch")
    cluster = proof.cluster
    requested_cluster = cluster_for_value(str(target.get("cluster_id") or target.get("cluster") or ""))
    if requested_cluster is not None and requested_cluster.id != cluster.id:
        raise ActionRequestValidationError("Dry-run proof target does not match requested cluster.", code="dry_run_target_mismatch")
    max_age = int(getattr(settings, "KUBERNETES_ADMIN_DRY_RUN_PROOF_MAX_AGE_SECONDS", 1800))
    if proof.created_at < timezone.now() - timedelta(seconds=max_age):
        raise ActionRequestValidationError("Dry-run proof has expired.", code="dry_run_proof_expired")
    proof_payload = proof.request_payload_sanitized if isinstance(proof.request_payload_sanitized, dict) else {}
    target_payload = proof_payload.get("target") if isinstance(proof_payload.get("target"), dict) else {}
    normalized = {
        "cluster_id": f"cluster_{cluster.id}",
        "cluster_name": cluster.name,
        "api_version": proof.resource_api_version,
        "kind": proof.resource_kind,
        "resource": target_payload.get("resource") or "",
        "namespace": proof.namespace,
        "name": proof.resource_name,
        "dry_run_action_id": dry_run_action_id,
        "manifest_fingerprint": proof_payload.get("manifest_fingerprint") or "",
        "dry_run_created_at": proof.created_at.isoformat(),
        "redacted": bool(proof_payload.get("redacted")),
    }
    return cluster, normalized, {
        "summary": summary,
        "blast_radius": "single_resource_apply",
        "affected": [{key: value for key, value in normalized.items() if key not in {"manifest_fingerprint"}}],
        "dry_run_proof": {
            "id": dry_run_action_id,
            "created_at": proof.created_at.isoformat(),
            "redacted": bool(proof_payload.get("redacted")),
            "submitted_top_level_fields": list(proof_payload.get("submitted_top_level_fields") or []),
        },
        "expected_verification": ["server-side apply completed", "resource generation observed", "recent warning events"],
    }


def resource_patch_preview(target: dict[str, Any], *, summary: str) -> tuple[K8sCluster, dict[str, Any], dict[str, Any]]:
    cluster = cluster_for_value(str(target.get("cluster_id") or target.get("cluster") or ""))
    if cluster is None:
        raise ActionRequestValidationError("cluster_id is required and must reference a known cluster.", code="cluster_required", payload={"target": target})
    ref = build_resource_ref(
        api_version=bounded_action_text(target.get("api_version") or "apps/v1", limit=80),
        kind=bounded_action_text(target.get("kind") or "", limit=80),
        namespace=bounded_action_text(target.get("namespace") or "", limit=120),
        name=bounded_action_text(target.get("name") or "", limit=180),
        resource=bounded_action_text(target.get("resource") or "", limit=120),
    )
    if not ref.namespace or not ref.name:
        raise ActionRequestValidationError("patch requires namespace, kind and name.", code="resource_target_required", payload={"target": target})
    patch_type, patch_body, shape = _clean_safe_patch_body(target)
    normalized = {
        "cluster_id": f"cluster_{cluster.id}",
        "cluster_name": cluster.name,
        "api_version": ref.api_version,
        "kind": ref.kind.lower(),
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
        "patch_type": patch_type,
        "patch_body": patch_body,
    }
    return cluster, normalized, {
        "summary": summary,
        "blast_radius": "single_resource_patch",
        "affected": [{key: value for key, value in normalized.items() if key != "patch_body"}],
        "patch_type": patch_type,
        "patch_shape": shape,
        "expected_verification": ["resource generation observed", "workload readiness if applicable", "recent warning events"],
    }


def resource_delete_preview(target: dict[str, Any], *, summary: str) -> tuple[K8sCluster, dict[str, Any], dict[str, Any]]:
    cluster = cluster_for_value(str(target.get("cluster_id") or target.get("cluster") or ""))
    if cluster is None:
        raise ActionRequestValidationError("cluster_id is required and must reference a known cluster.", code="cluster_required", payload={"target": target})
    ref = build_resource_ref(
        api_version=bounded_action_text(target.get("api_version") or "apps/v1", limit=80),
        kind=bounded_action_text(target.get("kind") or "", limit=80),
        namespace=bounded_action_text(target.get("namespace") or "", limit=120),
        name=bounded_action_text(target.get("name") or "", limit=180),
        resource=bounded_action_text(target.get("resource") or "", limit=120),
    )
    if not ref.namespace or not ref.name:
        raise ActionRequestValidationError("delete requires namespace, kind and name.", code="resource_target_required", payload={"target": target})
    if ref.kind in PROTECTED_CLUSTER_KINDS:
        raise ActionRequestValidationError("This resource kind cannot be deleted through action requests.", code="delete_kind_blocked", payload={"kind": ref.kind})
    if ref.namespace in protected_delete_namespaces():
        raise ActionRequestValidationError("Deletes in protected namespaces are blocked.", code="delete_namespace_protected", payload={"namespace": ref.namespace})
    expected_confirmation = expected_delete_confirmation(ref)
    confirmation = bounded_action_text(target.get("confirmation") or "", limit=240)
    if confirmation != expected_confirmation:
        raise ActionRequestValidationError("Exact delete confirmation is required.", code="delete_confirmation_mismatch", payload={"expected_confirmation": expected_confirmation})
    propagation_policy = _clean_delete_propagation_policy(target.get("propagation_policy") or "")
    normalized = {
        "cluster_id": f"cluster_{cluster.id}",
        "cluster_name": cluster.name,
        "api_version": ref.api_version,
        "kind": ref.kind,
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
        "confirmation": confirmation,
        "propagation_policy": propagation_policy,
    }
    return cluster, normalized, {
        "summary": summary,
        "blast_radius": "single_resource_delete",
        "affected": [{key: value for key, value in normalized.items() if key != "confirmation"}],
        "expected_confirmation": expected_confirmation,
        "propagation_policy": propagation_policy or "server_default",
        "expected_verification": ["resource no longer exists", "owner workload health", "recent warning events"],
    }


def _clean_safe_patch_body(target: dict[str, Any]) -> tuple[str, Any, dict[str, Any]]:
    patch_type = bounded_action_text(target.get("patch_type") or "merge", limit=20).lower()
    if patch_type not in PATCH_TYPES:
        raise ActionRequestValidationError("patch_type must be merge, strategic, or json.", code="patch_type_invalid", payload={"patch_type": patch_type})
    patch_body = target.get("patch_body")
    if patch_type == "json":
        if not isinstance(patch_body, list):
            raise ActionRequestValidationError("JSON patch body must be a list of operations.", code="patch_body_invalid")
        shape = {"body_shape": "json_patch", "operation_count": len(patch_body)}
    else:
        if not isinstance(patch_body, dict):
            raise ActionRequestValidationError("Patch body must be an object.", code="patch_body_invalid")
        shape = {"body_shape": "object", "top_level_fields": sorted(str(key)[:120] for key in patch_body.keys())}
    _assert_patch_body_size(patch_body)
    sanitized = sanitize_action_value(patch_body)
    if "[redacted]" in str(sanitized):
        raise ActionRequestValidationError("Patch body contains sensitive data and cannot be stored in an action request.", code="patch_body_sensitive")
    return patch_type, sanitized, shape


def _clean_delete_propagation_policy(value: Any) -> str:
    policy = bounded_action_text(value or "", limit=20)
    if not policy:
        return ""
    normalized = policy[:1].upper() + policy[1:].lower()
    if normalized not in {"Foreground", "Background", "Orphan"}:
        raise ActionRequestValidationError("propagation_policy must be Foreground, Background, or Orphan.", code="propagation_policy_invalid")
    return normalized


def _assert_patch_body_size(value: Any) -> None:
    try:
        encoded_size = len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ActionRequestValidationError("Patch body must be JSON serializable.", code="patch_body_invalid") from exc
    max_bytes = int(getattr(settings, "KUBERNETES_ADMIN_PATCH_MAX_BODY_BYTES", 65536))
    if encoded_size <= 0 or encoded_size > max_bytes:
        raise ActionRequestValidationError("Patch body is outside the allowed size.", code="patch_body_size_invalid", payload={"max_bytes": max_bytes})
