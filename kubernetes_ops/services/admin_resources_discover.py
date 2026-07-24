from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_api_discovery import api_resource_catalog_payload
from kubernetes_ops.services.admin_crd_discovery import crd_discovery_payload
from kubernetes_ops.services.admin_resource_catalog import build_resource_catalog, resource_catalog_action_summary
from kubernetes_ops.services.admin_resource_registry import common_resource_payload
from kubernetes_ops.services.admin_resource_sanitizer import sanitize_kubernetes_resource
from kubernetes_ops.services.admin_resources_helpers import (
    MAX_LIST_ITEMS,
    AdminResourceError,
    KubernetesResourceRef,
    _base_response,
    _cluster_payload,
    _provider_get,
    _provider_payload,
    _proxy_prefix,
    _public_path,
    _required_cluster,
    _required_rancher_provider,
    active_resource_session_for_user,
    rancher_api_path,
    rancher_resource_path,
    record_admin_resource_action,
)
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderTransport


def discover_cluster_resources(
    *, user, session_id: str, cluster_id: str, transport: ProviderTransport | None = None
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    session = active_resource_session_for_user(user, session_id, cluster, verb="list")
    provider = _required_rancher_provider(cluster)
    core_path = rancher_api_path(provider, cluster, "v1")
    groups_path = _proxy_prefix(provider, cluster) + "/apis"
    core = _provider_get(provider, core_path, transport=transport)
    groups = _provider_get(provider, groups_path, transport=transport)
    api_resources = api_resource_catalog_payload(
        core,
        groups,
        fetch_group_version=lambda version: _provider_get(
            provider, rancher_api_path(provider, cluster, version), transport=transport
        ),
        limit=MAX_LIST_ITEMS,
    )
    crd_resources = _discover_crd_resources(
        user=user, session_id=session_id, cluster=cluster, provider=provider, transport=transport
    )
    common_resources = common_resource_payload()
    resource_catalog = build_resource_catalog(
        common_resources=common_resources,
        api_resources=api_resources,
        crd_resources=crd_resources,
        limit=MAX_LIST_ITEMS,
    )
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=KubernetesResourceRef(api_version="v1", kind="APIResourceList", resource="apiresources"),
        verb=K8sAdminAction.VERB_LIST,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "core_count": len(core.get("resources", []) if isinstance(core.get("resources"), list) else []),
            "group_count": len(groups.get("groups", []) if isinstance(groups.get("groups"), list) else []),
            "api_resource_status": api_resources.get("status"),
            "api_resource_count": int(api_resources.get("item_count") or 0),
            **resource_catalog_action_summary(resource_catalog),
            "crd_status": crd_resources.get("status"),
            "crd_count": int(crd_resources.get("item_count") or 0),
        },
    )
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "discovery",
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "paths": {
            "core": _public_path(core_path),
            "groups": _public_path(groups_path),
            "crds": crd_resources.get("path", ""),
        },
        "core": sanitize_metadata(core),
        "groups": sanitize_metadata(groups),
        "api_resources": api_resources,
        "common_resources": common_resources,
        "crd_resources": crd_resources,
        "resource_catalog": resource_catalog,
    }


def list_cluster_crds(
    *, user, session_id: str, cluster_id: str, transport: ProviderTransport | None = None
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    session = active_resource_session_for_user(user, session_id, cluster, verb="list", kind="CustomResourceDefinition")
    provider = _required_rancher_provider(cluster)
    ref = KubernetesResourceRef(
        api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition", resource="customresourcedefinitions"
    )
    path = rancher_resource_path(provider, cluster, ref)
    payload = _provider_get(provider, path, transport=transport)
    items = [sanitize_kubernetes_resource(item) for item in payload_items(payload)[:MAX_LIST_ITEMS]]
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_LIST,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={"item_count": len(items)},
    )
    return _base_response(
        "crd_list",
        cluster,
        provider,
        ref,
        path,
        {"items": items, "item_count": len(items), "truncated": len(payload_items(payload)) > MAX_LIST_ITEMS},
    )


def _discover_crd_resources(
    *, user, session_id: str, cluster: K8sCluster, provider: K8sProvider, transport: ProviderTransport | None
) -> dict[str, Any]:
    ref = KubernetesResourceRef(
        api_version="apiextensions.k8s.io/v1", kind="CustomResourceDefinition", resource="customresourcedefinitions"
    )
    path = rancher_resource_path(provider, cluster, ref)
    try:
        active_resource_session_for_user(user, session_id, cluster, verb="list", kind="CustomResourceDefinition")
        payload = _provider_get(provider, path, transport=transport)
    except AdminResourceError as exc:
        return {
            "status": "unavailable",
            "reason": exc.code,
            "path": _public_path(path),
            "items": [],
            "item_count": 0,
            "truncated": False,
            "schema_included": False,
        }
    return {"path": _public_path(path), **crd_discovery_payload(payload, limit=MAX_LIST_ITEMS)}
