from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from django.utils import timezone

from kubernetes_ops.models import K8sAdminSession
from kubernetes_ops.services.admin_delete import DEFAULT_PROTECTED_NAMESPACES
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.readonly_rbac import _to_yaml

BASE_READ_RULES: tuple[dict[str, Any], ...] = (
    {"apiGroups": [""], "resources": ["pods", "pods/log", "services", "events"], "verbs": ["get", "list", "watch"]},
    {"apiGroups": ["apps"], "resources": ["deployments", "replicasets", "statefulsets", "daemonsets"], "verbs": ["get", "list", "watch"]},
)
TERMINAL_SUBRESOURCE_RULES = {
    "exec": {"apiGroups": [""], "resources": ["pods/exec"], "verbs": ["create"]},
    "port_forward": {"apiGroups": [""], "resources": ["pods/portforward"], "verbs": ["create"]},
}
DENIED_RESOURCES = {"secrets", "nodes", "nodes/proxy", "nodes/debug", "pods/attach"}
DENIED_BASE_WRITE_VERBS = {"create", "update", "patch", "delete", "deletecollection", "escalate", "bind", "impersonate"}


def build_restricted_kube_context_for_session(*, session: K8sAdminSession, include_manifest: bool = False) -> dict[str, Any]:
    session = refresh_admin_session_state(session)
    _validate_session(session)
    namespace = _single_namespace(session)
    service_account_name = _safe_name(f"webterm-bg-{str(session.session_id)[:8]}")
    role_name = f"{service_account_name}-role"
    binding_name = f"{service_account_name}-binding"
    ttl_seconds = max(1, int((session.expires_at - timezone.now()).total_seconds()))
    rules = _rules_for_session(session)
    bundle = {
        "namespace": namespace,
        "service_account_name": service_account_name,
        "role_name": role_name,
        "binding_name": binding_name,
        "manifests": _manifests(
            session=session,
            namespace=namespace,
            service_account_name=service_account_name,
            role_name=role_name,
            binding_name=binding_name,
            rules=rules,
            ttl_seconds=ttl_seconds,
        ),
    }
    validation = validate_restricted_kube_context_bundle(bundle)
    report = {
        "status": validation["status"],
        "mode": "restricted_break_glass_context",
        "session_id": str(session.session_id),
        "cluster_id": f"cluster_{session.cluster_id}" if session.cluster_id else "",
        "cluster_name": session.cluster.name if session.cluster_id else "",
        "namespace": namespace,
        "service_account_name": service_account_name,
        "role_name": role_name,
        "binding_name": binding_name,
        "ttl_seconds": ttl_seconds,
        "expires_at": session.expires_at.isoformat(),
        "rules": deepcopy(rules),
        "validation": validation,
        "terminal_bridge_enabled": False,
        "node_debug_enabled": False,
        "applies_manifest": False,
        "contains_kubeconfig": False,
        "contains_token": False,
    }
    if include_manifest:
        report["manifest_yaml"] = render_restricted_kube_context_yaml(bundle)
    return report


def validate_restricted_kube_context_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    manifests = bundle.get("manifests") if isinstance(bundle, dict) else None
    if not isinstance(manifests, list):
        return {"status": "missing", "errors": ["manifests_missing"]}
    errors: list[str] = []
    kinds = {str(item.get("kind") or "") for item in manifests if isinstance(item, dict)}
    for required in {"ServiceAccount", "Role", "RoleBinding"}:
        if required not in kinds:
            errors.append(f"missing:{required}")
    if "ClusterRole" in kinds or "ClusterRoleBinding" in kinds:
        errors.append("cluster_scoped_rbac_forbidden")
    for manifest in manifests:
        if not isinstance(manifest, dict):
            continue
        metadata = manifest.get("metadata") or {}
        if metadata.get("namespace") != bundle.get("namespace"):
            errors.append(f"{manifest.get('kind')}:namespace_mismatch")
        if manifest.get("kind") == "Role":
            errors.extend(_validate_rules(manifest.get("rules") or []))
    if not _role_binding_matches(bundle):
        errors.append("role_binding_mismatch")
    return {"status": "ready" if not errors else "missing", "errors": errors}


def render_restricted_kube_context_yaml(bundle: dict[str, Any]) -> str:
    return "\n---\n".join(_to_yaml(item) for item in bundle["manifests"]) + "\n"


def _validate_session(session: K8sAdminSession) -> None:
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Active break-glass admin session is required.", code="admin_break_glass_session_not_active", status=403)
    if session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminResourceError("Restricted kube context requires a break-glass admin session.", code="break_glass_session_required", status=403)
    if session.cluster_id is None:
        raise AdminResourceError("Restricted kube context requires a scoped cluster.", code="admin_session_cluster_required", status=403)
    assert_admin_session_approved(session=session, action="cluster_terminal")


def _single_namespace(session: K8sAdminSession) -> str:
    candidates = [str(item or "").strip() for item in session.allowed_namespaces or [] if str(item or "").strip()]
    namespace = str(session.namespace or "").strip() or (candidates[0] if candidates else "")
    scoped = set(candidates) if candidates else ({namespace} if namespace else set())
    if not namespace or namespace == "*" or "*" in scoped or len(scoped) != 1 or namespace not in scoped:
        raise AdminResourceError("Restricted kube context requires exactly one namespace.", code="restricted_context_namespace_required", status=403)
    if namespace in set(DEFAULT_PROTECTED_NAMESPACES):
        raise AdminResourceError("Restricted kube context is blocked in protected namespaces.", code="restricted_context_namespace_protected", status=403)
    return namespace


def _rules_for_session(session: K8sAdminSession) -> list[dict[str, Any]]:
    allowed_verbs = set(session.allowed_verbs or [])
    rules = [deepcopy(rule) for rule in BASE_READ_RULES]
    for verb, rule in TERMINAL_SUBRESOURCE_RULES.items():
        if verb in allowed_verbs:
            rules.append(deepcopy(rule))
    if len(rules) == len(BASE_READ_RULES):
        raise AdminResourceError("Restricted kube context requires exec or port-forward in the session scope.", code="restricted_context_terminal_verbs_required", status=403)
    return rules


def _manifests(*, session: K8sAdminSession, namespace: str, service_account_name: str, role_name: str, binding_name: str, rules: list[dict[str, Any]], ttl_seconds: int) -> list[dict[str, Any]]:
    metadata = {
        "labels": {
            "app.kubernetes.io/part-of": "webterm-kubernetes-admin",
            "webterm.io/admin-session": str(session.session_id),
        },
        "annotations": {
            "webterm.io/purpose": "restricted-break-glass-context",
            "webterm.io/expires-at": session.expires_at.isoformat(),
            "webterm.io/ttl-seconds": str(ttl_seconds),
        },
    }
    return [
        {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": service_account_name, "namespace": namespace, **deepcopy(metadata)}},
        {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "Role", "metadata": {"name": role_name, "namespace": namespace, **deepcopy(metadata)}, "rules": deepcopy(rules)},
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": binding_name, "namespace": namespace, **deepcopy(metadata)},
            "subjects": [{"kind": "ServiceAccount", "name": service_account_name, "namespace": namespace}],
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": role_name},
        },
    ]


def _validate_rules(rules: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for rule in rules:
        resources = set(rule.get("resources") or [])
        verbs = set(rule.get("verbs") or [])
        if "*" in resources or "*" in verbs:
            errors.append("rule:wildcard_forbidden")
        if resources & DENIED_RESOURCES:
            errors.append("rule:denied_resources:" + ",".join(sorted(resources & DENIED_RESOURCES)))
        illegal_base_writes = {verb for verb in verbs & DENIED_BASE_WRITE_VERBS if not resources <= {"pods/exec", "pods/portforward"}}
        if illegal_base_writes:
            errors.append("rule:base_write_verbs:" + ",".join(sorted(illegal_base_writes)))
    return errors


def _role_binding_matches(bundle: dict[str, Any]) -> bool:
    bindings = [item for item in bundle.get("manifests", []) if isinstance(item, dict) and item.get("kind") == "RoleBinding"]
    for binding in bindings:
        subjects = binding.get("subjects") or []
        role_ref = binding.get("roleRef") or {}
        if role_ref.get("kind") != "Role" or role_ref.get("name") != bundle.get("role_name"):
            continue
        if any(item.get("kind") == "ServiceAccount" and item.get("name") == bundle.get("service_account_name") and item.get("namespace") == bundle.get("namespace") for item in subjects if isinstance(item, dict)):
            return True
    return False


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^a-z0-9.-]+", "-", str(value or "").lower()).strip("-.")
    return safe[:63] or "webterm-bg"
