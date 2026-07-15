from __future__ import annotations

import urllib.parse
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_dry_run import FIELD_MANAGER, manifest_fingerprint
from kubernetes_ops.services.admin_owner_guard import assert_direct_admin_mutation_allowed
from kubernetes_ops.services.admin_ownership import build_admin_resource_ownership
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    build_resource_ref,
    cluster_for_value,
    rancher_resource_path,
    resource_was_redacted,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved, assert_production_write_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport


def apply_kubernetes_resource(
    *,
    user,
    session_id: str,
    cluster_id: str,
    dry_run_action_id: str,
    reason: str,
    manifest: dict[str, Any],
    namespace: str = "",
    resource: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED", False)):
        raise AdminResourceError("Native Kubernetes apply is disabled by policy.", code="native_apply_disabled", status=403)
    cluster = _required_cluster(cluster_id)
    ref = _ref_from_manifest(manifest, namespace=namespace, resource=resource)
    session = _active_apply_session_for_user(user, session_id, cluster, ref=ref)
    reason_value = str(reason or "").strip()[:1000]
    if not reason_value:
        raise AdminResourceError("reason is required for apply.", code="reason_required")
    assert_production_write_approved(session=session, cluster=cluster, ref=ref, action="apply")
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_APPLY)
    proof = None if _session_uses_break_glass_apply_bypass(session) else _required_dry_run_proof(dry_run_action_id, session=session, cluster=cluster, ref=ref, manifest=manifest)
    provider = _required_rancher_provider(cluster)
    path = _apply_path(rancher_resource_path(provider, cluster, ref))
    sanitized_submitted = sanitize_kubernetes_resource(manifest)
    assert_direct_admin_mutation_allowed(cluster=cluster, ref=ref, action="apply", resource=sanitized_submitted)

    try:
        response = ProviderJsonClient(provider, transport=transport).request(
            "PATCH",
            path,
            body=manifest,
            extra_headers={"Content-Type": "application/apply-patch+yaml", "Accept": "application/json"},
        )
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        _record_apply_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            submitted=sanitized_submitted,
            proof=proof,
            reason=reason_value,
            status=K8sAdminAction.STATUS_FAILED,
            response_summary={
                "source": "provider_error",
                "error": str(exc),
                **_proof_response_summary(proof, session=session),
            },
        )
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc

    sanitized_response = sanitize_kubernetes_resource(response)
    redacted = resource_was_redacted(sanitized_submitted) or resource_was_redacted(sanitized_response)
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=sanitized_response or sanitized_submitted)
    action = _record_apply_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        submitted=sanitized_submitted,
        proof=proof,
        reason=reason_value,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "source": "rancher_kubernetes_apply",
            "redacted": redacted,
            "ownership_owner": ownership.get("owner"),
            "server_top_level_fields": sorted(sanitized_response.keys()),
            **_proof_response_summary(proof, session=session),
        },
    )
    return {
        "success": True,
        "mode": "admin_write_apply",
        "operation": "apply",
        "dry_run": False,
        "mutates_state": True,
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "path": _public_path(path),
        "resource": sanitized_response,
        "redacted": redacted,
        "ownership": ownership,
        "dry_run_proof": _proof_payload(proof),
        "break_glass": _session_uses_break_glass_apply_bypass(session),
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "mutates_state": True,
            "requires_active_admin_session": True,
            "requires_write_session": session.mode == K8sAdminSession.MODE_WRITE,
            "requires_break_glass_session": session.mode == K8sAdminSession.MODE_BREAK_GLASS,
            "requires_dry_run_proof": not _session_uses_break_glass_apply_bypass(session),
            "dry_run_bypassed": _session_uses_break_glass_apply_bypass(session),
            "blocked_actions": ["patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
    }


def _active_apply_session_for_user(user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not (policy["can_apply_yaml"] or policy.get("can_break_glass_apply")):
        if policy["can_break_glass"] and bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED", False)):
            code = "break_glass_apply_disabled"
        elif policy["can_admin_write"] or policy["can_break_glass"]:
            code = "native_apply_disabled"
        else:
            code = "admin_write_required"
        raise AdminResourceError("Kubernetes apply access is required.", code=code, status=403)
    try:
        session = K8sAdminSession.objects.select_related("user", "provider", "cluster").filter(session_id=session_id, user=user).first()
    except (TypeError, ValueError) as exc:
        raise AdminResourceError("Active write admin session is required.", code="admin_write_session_required", status=403) from exc
    if session is None:
        raise AdminResourceError("Active write admin session is required.", code="admin_write_session_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Write admin session is not active.", code="admin_write_session_not_active", status=403)
    if session.mode == K8sAdminSession.MODE_WRITE:
        if not policy["can_apply_yaml"]:
            raise AdminResourceError("Kubernetes apply access is required.", code="native_apply_disabled", status=403)
    elif session.mode == K8sAdminSession.MODE_BREAK_GLASS:
        if not policy.get("can_break_glass_apply"):
            raise AdminResourceError("Break-glass apply bypass is disabled by policy.", code="break_glass_apply_disabled", status=403)
    else:
        raise AdminResourceError("Apply requires a write or break-glass admin session.", code="write_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if K8sAdminAction.VERB_APPLY not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow apply.", code="admin_session_verb_denied", status=403)
    _check_session_scope(session, ref)
    return session


def _required_dry_run_proof(
    action_id: str,
    *,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    manifest: dict[str, Any],
) -> K8sAdminAction:
    if not str(action_id or "").strip():
        raise AdminResourceError("dry_run_action_id is required before apply.", code="dry_run_proof_required", status=409)
    try:
        proof = K8sAdminAction.objects.filter(
            action_id=action_id,
            session=session,
            cluster=cluster,
            verb=K8sAdminAction.VERB_DRY_RUN_APPLY,
            status=K8sAdminAction.STATUS_DRY_RUN,
        ).first()
    except (TypeError, ValueError, ValidationError) as exc:
        raise AdminResourceError("Valid dry_run_action_id is required before apply.", code="dry_run_proof_required", status=409) from exc
    if proof is None:
        raise AdminResourceError("Successful dry-run proof is required before apply.", code="dry_run_proof_required", status=409)
    if proof.resource_api_version != ref.api_version or proof.resource_kind != ref.kind or proof.namespace != ref.namespace or proof.resource_name != ref.name:
        raise AdminResourceError("Dry-run proof target does not match apply target.", code="dry_run_target_mismatch", status=409)
    max_age = int(getattr(settings, "KUBERNETES_ADMIN_DRY_RUN_PROOF_MAX_AGE_SECONDS", 1800))
    if proof.created_at < timezone.now() - timedelta(seconds=max_age):
        raise AdminResourceError("Dry-run proof has expired.", code="dry_run_proof_expired", status=409)
    expected = str((proof.request_payload_sanitized or {}).get("manifest_fingerprint") or "")
    if not expected or expected != manifest_fingerprint(manifest):
        raise AdminResourceError("Manifest changed after dry-run.", code="dry_run_manifest_mismatch", status=409)
    return proof


def _session_uses_break_glass_apply_bypass(session: K8sAdminSession) -> bool:
    return session.mode == K8sAdminSession.MODE_BREAK_GLASS


def _proof_payload(proof: K8sAdminAction | None) -> dict[str, Any] | None:
    if proof is None:
        return None
    return {"id": str(proof.action_id), "created_at": proof.created_at.isoformat()}


def _proof_response_summary(proof: K8sAdminAction | None, *, session: K8sAdminSession) -> dict[str, Any]:
    if proof is None:
        return {
            "dry_run_bypassed": True,
            "break_glass": _session_uses_break_glass_apply_bypass(session),
            "break_glass_session_id": str(session.session_id),
            "approval_ref": session.approval_ref,
        }
    return {"dry_run_action_id": str(proof.action_id), "dry_run_bypassed": False}


def _check_session_scope(session: K8sAdminSession, ref: KubernetesResourceRef) -> None:
    if ref.namespace:
        allowed_namespaces = set(session.allowed_namespaces or [])
        if "*" not in allowed_namespaces and ref.namespace not in allowed_namespaces:
            raise AdminResourceError("Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403)
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds:
        raise AdminResourceError("Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403)


def _ref_from_manifest(manifest: dict[str, Any], *, namespace: str, resource: str) -> KubernetesResourceRef:
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    api_version = str(manifest.get("apiVersion") or "").strip()
    kind = str(manifest.get("kind") or "").strip()
    name = str(metadata.get("name") or "").strip()
    if not api_version:
        raise AdminResourceError("manifest.apiVersion is required.", code="api_version_required")
    if not kind:
        raise AdminResourceError("manifest.kind is required.", code="kind_required")
    if not name:
        raise AdminResourceError("manifest.metadata.name is required for apply.", code="resource_name_required")
    return build_resource_ref(
        api_version=api_version,
        kind=kind,
        namespace=str(metadata.get("namespace") or namespace or "").strip(),
        name=name,
        resource=resource,
    )


def _apply_path(path: str) -> str:
    query = urllib.parse.urlencode({"fieldManager": FIELD_MANAGER})
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{query}"


def _record_apply_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    submitted: dict[str, Any],
    proof: K8sAdminAction | None,
    reason: str,
    status: str,
    response_summary: dict[str, Any],
) -> K8sAdminAction:
    return K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace=ref.namespace,
        resource_api_version=ref.api_version,
        resource_kind=ref.kind,
        resource_name=ref.name,
        verb=K8sAdminAction.VERB_APPLY,
        status=status,
        request_payload_sanitized={
            "target": _target_payload(ref),
            "reason": reason,
            **_proof_response_summary(proof, session=session),
            "redacted": resource_was_redacted(submitted),
            "manifest_fingerprint": manifest_fingerprint(submitted),
            "submitted_top_level_fields": sorted(submitted.keys()),
        },
        diff_summary=sanitize_metadata(proof.diff_summary if proof is not None else {"available": False, "reason": "break_glass_dry_run_bypass"}),
        response_summary=sanitize_metadata(response_summary),
    )


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode apply.", code="rancher_provider_required", status=409)
    return provider


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _target_payload(ref: KubernetesResourceRef) -> dict[str, Any]:
    return {
        "api_version": ref.api_version,
        "kind": ref.kind,
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
    }


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
