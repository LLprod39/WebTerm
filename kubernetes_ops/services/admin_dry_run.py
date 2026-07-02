from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from typing import Any

import yaml

from django.conf import settings

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
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
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport


FIELD_MANAGER = "webterm-admin-mode"
DIFF_MAX_CHANGES = 80
DIFF_MAX_OBJECT_KEYS = 20
DIFF_MAX_VALUE_STRING = 200


def manifest_fingerprint(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    secret = str(getattr(settings, "SECRET_KEY", "webterm")).encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def dry_run_apply_kubernetes_resource(
    *,
    user,
    session_id: str,
    cluster_id: str,
    manifest: Any = None,
    manifest_yaml: str = "",
    namespace: str = "",
    resource: str = "",
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    submitted = _parse_manifest(manifest=manifest, manifest_yaml=manifest_yaml)
    ref = _ref_from_manifest(submitted, namespace=namespace, resource=resource)
    session = _active_write_session_for_user(user, session_id, cluster, ref=ref)
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_DRY_RUN_APPLY)
    provider = _required_rancher_provider(cluster)
    path = _dry_run_path(rancher_resource_path(provider, cluster, ref))
    submitted_fingerprint = manifest_fingerprint(submitted)

    sanitized_submitted = sanitize_kubernetes_resource(submitted)
    try:
        response = ProviderJsonClient(provider, transport=transport).request(
            "PATCH",
            path,
            body=submitted,
            extra_headers={"Content-Type": "application/apply-patch+yaml", "Accept": "application/json"},
        )
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        _record_dry_run_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=ref,
            submitted=sanitized_submitted,
            response={},
            status=K8sAdminAction.STATUS_FAILED,
            manifest_fingerprint_value=submitted_fingerprint,
            response_summary={"source": "provider_error", "error": str(exc), "dry_run": True},
        )
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc

    sanitized_response = sanitize_kubernetes_resource(response)
    redacted = resource_was_redacted(sanitized_submitted) or resource_was_redacted(sanitized_response)
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=sanitized_response or sanitized_submitted)
    diff_summary = _diff_summary(sanitized_submitted, sanitized_response, redacted=redacted)
    diff = _structured_diff(sanitized_submitted, sanitized_response, redacted=redacted)
    action = _record_dry_run_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        submitted=sanitized_submitted,
        response=sanitized_response,
        status=K8sAdminAction.STATUS_DRY_RUN,
        diff_summary=diff_summary,
        manifest_fingerprint_value=submitted_fingerprint,
        response_summary={
            "source": "rancher_kubernetes_dry_run",
            "dry_run": True,
            "redacted": redacted,
            "ownership_owner": ownership.get("owner"),
            "changed_top_level_fields": diff_summary["changed_top_level_fields"],
            "diff_change_count": diff["change_count"],
            "diff_truncated": diff["truncated"],
        },
    )
    return {
        "success": True,
        "mode": "admin_write_preview",
        "operation": "dry_run_apply",
        "dry_run": True,
        "mutates_state": False,
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": _target_payload(ref),
        "path": _public_path(path),
        "resource": sanitized_response,
        "submitted": sanitized_submitted,
        "redacted": redacted,
        "diff_summary": diff_summary,
        "diff": diff,
        "ownership": ownership,
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "requires_write_session": True,
            "server_side_dry_run": True,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
    }


def _active_write_session_for_user(user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy["can_admin_write"]:
        raise AdminResourceError("Kubernetes admin write access is required.", code="admin_write_required", status=403)
    try:
        session = K8sAdminSession.objects.select_related("user", "provider", "cluster").filter(session_id=session_id, user=user).first()
    except (TypeError, ValueError) as exc:
        raise AdminResourceError("Active write admin session is required.", code="admin_write_session_required", status=403) from exc
    if session is None:
        raise AdminResourceError("Active write admin session is required.", code="admin_write_session_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Write admin session is not active.", code="admin_write_session_not_active", status=403)
    if session.mode != K8sAdminSession.MODE_WRITE:
        raise AdminResourceError("Dry-run apply requires a write admin session.", code="write_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if K8sAdminAction.VERB_DRY_RUN_APPLY not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow dry-run apply.", code="admin_session_verb_denied", status=403)
    _check_session_scope(session, ref)
    return session


def _check_session_scope(session: K8sAdminSession, ref: KubernetesResourceRef) -> None:
    if ref.namespace:
        allowed_namespaces = set(session.allowed_namespaces or [])
        if "*" not in allowed_namespaces and ref.namespace not in allowed_namespaces:
            raise AdminResourceError("Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403)
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds:
        raise AdminResourceError("Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403)


def _parse_manifest(*, manifest: Any, manifest_yaml: str) -> dict[str, Any]:
    if isinstance(manifest, dict):
        parsed = manifest
    else:
        text = str(manifest_yaml or "").strip()
        if not text:
            raise AdminResourceError("manifest_yaml or manifest object is required.", code="manifest_required")
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise AdminResourceError("Manifest YAML is invalid.", code="manifest_yaml_invalid", payload={"detail": str(exc)[:500]}) from exc
    if not isinstance(parsed, dict):
        raise AdminResourceError("Manifest must be a Kubernetes object.", code="manifest_object_required")
    return parsed


def _ref_from_manifest(manifest: dict[str, Any], *, namespace: str, resource: str) -> KubernetesResourceRef:
    api_version = str(manifest.get("apiVersion") or "").strip()
    kind = str(manifest.get("kind") or "").strip()
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    name = str(metadata.get("name") or "").strip()
    namespace_value = str(metadata.get("namespace") or namespace or "").strip()
    if not api_version:
        raise AdminResourceError("manifest.apiVersion is required.", code="api_version_required")
    if not kind:
        raise AdminResourceError("manifest.kind is required.", code="kind_required")
    if not name:
        raise AdminResourceError("manifest.metadata.name is required for dry-run apply.", code="resource_name_required")
    return build_resource_ref(api_version=api_version, kind=kind, namespace=namespace_value, name=name, resource=resource)


def _dry_run_path(path: str) -> str:
    query = urllib.parse.urlencode({"dryRun": "All", "fieldManager": FIELD_MANAGER})
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{query}"


def _diff_summary(submitted: dict[str, Any], response: dict[str, Any], *, redacted: bool) -> dict[str, Any]:
    submitted_keys = set(submitted.keys())
    response_keys = set(response.keys())
    common_keys = submitted_keys & response_keys
    return {
        "available": bool(response),
        "redacted": redacted,
        "submitted_top_level_fields": sorted(submitted_keys),
        "server_top_level_fields": sorted(response_keys),
        "changed_top_level_fields": sorted(key for key in common_keys if submitted.get(key) != response.get(key)),
        "server_added_top_level_fields": sorted(response_keys - submitted_keys),
        "server_removed_top_level_fields": sorted(submitted_keys - response_keys),
    }


def _structured_diff(submitted: dict[str, Any], response: dict[str, Any], *, redacted: bool) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    state = {"truncated": False}
    if response:
        _collect_diff_changes(submitted, response, path="", changes=changes, state=state)
    return {
        "available": bool(response),
        "redacted": redacted,
        "truncated": bool(state["truncated"]),
        "change_count": len(changes),
        "max_changes": DIFF_MAX_CHANGES,
        "changes": changes,
    }


def _collect_diff_changes(before: Any, after: Any, *, path: str, changes: list[dict[str, Any]], state: dict[str, bool]) -> None:
    if state["truncated"]:
        return
    if before == after:
        return
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before.keys()) | set(after.keys()), key=str)
        for raw_key in keys:
            key = str(raw_key)
            child_path = _json_pointer(path, key)
            if raw_key not in before:
                _append_diff_change(changes, state, path=child_path, operation="added", before=None, after=after.get(raw_key))
            elif raw_key not in after:
                _append_diff_change(changes, state, path=child_path, operation="removed", before=before.get(raw_key), after=None)
            else:
                _collect_diff_changes(before.get(raw_key), after.get(raw_key), path=child_path, changes=changes, state=state)
            if state["truncated"]:
                return
        return
    if isinstance(before, list) or isinstance(after, list):
        _append_diff_change(changes, state, path=path or "/", operation="changed", before=before, after=after)
        return
    _append_diff_change(changes, state, path=path or "/", operation="changed", before=before, after=after)


def _append_diff_change(
    changes: list[dict[str, Any]],
    state: dict[str, bool],
    *,
    path: str,
    operation: str,
    before: Any,
    after: Any,
) -> None:
    if len(changes) >= DIFF_MAX_CHANGES:
        state["truncated"] = True
        return
    changes.append(
        {
            "path": path[:500],
            "operation": operation,
            "before": _diff_value_summary(before),
            "after": _diff_value_summary(after),
        }
    )


def _diff_value_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null", "value": None}
    if value == "[redacted]":
        return {"type": "redacted", "value": "[redacted]"}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"type": "number", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": _bounded_string(value)}
    if isinstance(value, list):
        return {"type": "array", "length": len(value)}
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value.keys())
        return {
            "type": "object",
            "key_count": len(keys),
            "keys": keys[:DIFF_MAX_OBJECT_KEYS],
        }
    return {"type": type(value).__name__, "value": _bounded_string(str(value))}


def _bounded_string(value: str) -> str:
    text = str(value or "")
    if len(text) > DIFF_MAX_VALUE_STRING:
        return f"{text[:DIFF_MAX_VALUE_STRING]}...[truncated]"
    return text


def _json_pointer(base: str, token: str) -> str:
    escaped = token.replace("~", "~0").replace("/", "~1")
    return f"{base}/{escaped}" if base else f"/{escaped}"


def _record_dry_run_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    submitted: dict[str, Any],
    response: dict[str, Any],
    status: str,
    manifest_fingerprint_value: str,
    diff_summary: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None,
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
        verb=K8sAdminAction.VERB_DRY_RUN_APPLY,
        status=status,
        request_payload_sanitized={
            "target": _target_payload(ref),
            "dry_run": True,
            "redacted": resource_was_redacted(submitted),
            "manifest_fingerprint": manifest_fingerprint_value,
            "submitted_top_level_fields": sorted(submitted.keys()),
        },
        diff_summary=sanitize_metadata(diff_summary or _diff_summary(submitted, response, redacted=resource_was_redacted(submitted))),
        response_summary=sanitize_metadata(response_summary or {}),
    )


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode dry-run apply.", code="rancher_provider_required", status=409)
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
