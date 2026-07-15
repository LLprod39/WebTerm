from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sAppRef, K8sCluster
from kubernetes_ops.services.admin_ownership import build_admin_resource_ownership
from kubernetes_ops.services.admin_resources import AdminResourceError, KubernetesResourceRef

GUARDED_OWNERS = {K8sAppRef.OWNER_DEVTRON, K8sAppRef.OWNER_FLEET, K8sAppRef.OWNER_EXTERNAL}


def assert_direct_admin_mutation_allowed(
    *,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    action: str,
    resource: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ownership = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=resource)
    owner = str(ownership.get("owner") or "")
    if owner in GUARDED_OWNERS:
        raise AdminResourceError(
            "Direct mutation is blocked for this owner. Use the owner workflow instead.",
            code="owner_direct_mutation_blocked",
            status=409,
            payload={
                "action": str(action or ""),
                "owner": owner,
                "change_path": ownership.get("change_path"),
                "direct_apply_policy": ownership.get("direct_apply_policy"),
                "warnings": ownership.get("warnings") or [],
                "evidence": ownership.get("evidence") or [],
                "target": {
                    "api_version": ref.api_version,
                    "kind": ref.kind,
                    "resource": ref.resource,
                    "namespace": ref.namespace,
                    "name": ref.name,
                },
            },
        )
    return ownership
