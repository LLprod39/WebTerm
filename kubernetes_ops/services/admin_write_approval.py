from __future__ import annotations

from django.conf import settings

from kubernetes_ops.models import K8sAdminSession, K8sCluster
from kubernetes_ops.permissions import kubernetes_admin_mode_enabled
from kubernetes_ops.services.admin_resources import AdminResourceError, KubernetesResourceRef
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS

DEFAULT_PRODUCTION_ENVIRONMENTS = {"prod", "production"}
DEFAULT_PRODUCTION_NAMESPACES = {"prod", "production"}
RESTRICTED_CREDENTIAL_EVIDENCE_SETTING = "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF"


def assert_admin_session_approved(*, session: K8sAdminSession, action: str) -> None:
    if not kubernetes_admin_mode_enabled():
        raise AdminResourceError("Kubernetes Admin Mode is disabled.", code="admin_mode_disabled", status=403)
    if admin_session_has_approval(session):
        return
    raise AdminResourceError(
        "Approved admin session is required.",
        code="admin_session_approval_required",
        status=403,
        payload={
            "action": action,
            "session_id": str(session.session_id),
            "requires": ["approval_ref", "approved_by", "approved_at"],
        },
    )


def assert_production_write_approved(
    *,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    action: str,
) -> None:
    if not production_approval_required(cluster=cluster, namespace=ref.namespace):
        return
    if admin_session_has_approval(session):
        gate = production_write_restricted_credential_gate_report(cluster=cluster, namespace=ref.namespace)
        if gate["required"] and not gate["ready"]:
            raise AdminResourceError(
                "Production Kubernetes writes require restricted credential evidence.",
                code="restricted_credential_evidence_required",
                status=403,
                payload={
                    "action": action,
                    "cluster": cluster.name,
                    "environment": cluster.environment,
                    "namespace": ref.namespace,
                    "target_environment": gate["target_environment"],
                    "requires": [RESTRICTED_CREDENTIAL_EVIDENCE_SETTING],
                },
            )
        return
    raise AdminResourceError(
        "Production Kubernetes writes require an approved admin session.",
        code="production_approval_required",
        status=403,
        payload={
            "action": action,
            "cluster": cluster.name,
            "environment": cluster.environment,
            "namespace": ref.namespace,
            "requires": ["approval_ref", "approved_by", "approved_at"],
        },
    )


def admin_session_has_approval(session: K8sAdminSession) -> bool:
    return bool(session.approval_ref and session.approved_at and session.approved_by_id)


def production_approval_required(*, cluster: K8sCluster, namespace: str) -> bool:
    return _environment_requires_approval(cluster.environment) or _namespace_requires_approval(namespace)


def production_write_restricted_credential_gate_report(
    *,
    cluster: K8sCluster,
    namespace: str,
    target_environment: str | None = None,
    evidence_ref: str | None = None,
) -> dict[str, object]:
    environment = _release_environment(target_environment)
    required = bool(
        environment in PRODUCTION_ENVIRONMENTS
        and production_approval_required(cluster=cluster, namespace=namespace)
    )
    present = bool(_restricted_credential_evidence_ref(evidence_ref))
    ready = bool(not required or present)
    return {
        "status": "ready" if ready else "missing",
        "required": required,
        "ready": ready,
        "target_environment": environment,
        "cluster_environment": str(cluster.environment or ""),
        "namespace": namespace,
        "setting": RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
        "evidence_ref_present": present,
        "blocker": "" if ready else "restricted_credential_evidence_required",
    }


def _release_environment(value: str | None = None) -> str:
    raw = getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") if value is None else value
    normalized = str(raw or "local").strip().lower()
    return normalized or "local"


def _restricted_credential_evidence_ref(value: str | None = None) -> str:
    raw = getattr(settings, RESTRICTED_CREDENTIAL_EVIDENCE_SETTING, "") if value is None else value
    return str(raw or "").strip()


def _environment_requires_approval(environment: str) -> bool:
    return str(environment or "").strip().lower() in DEFAULT_PRODUCTION_ENVIRONMENTS


def _namespace_requires_approval(namespace: str) -> bool:
    value = str(namespace or "").strip().lower()
    if not value:
        return False
    return value in DEFAULT_PRODUCTION_NAMESPACES or value.startswith("prod-") or value.endswith("-prod") or value.startswith("production-") or value.endswith("-production")
