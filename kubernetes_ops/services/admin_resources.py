from __future__ import annotations

from kubernetes_ops.services.admin_resource_registry import COMMON_RESOURCES
from kubernetes_ops.services.admin_resource_sanitizer import resource_was_redacted, sanitize_kubernetes_resource
from kubernetes_ops.services.admin_resources_discover import (
    discover_cluster_resources,
    list_cluster_crds,
)
from kubernetes_ops.services.admin_resources_helpers import (
    MAX_LIST_ITEMS,
    READ_VERBS,
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    build_resource_ref,
    cluster_for_value,
    rancher_api_path,
    rancher_resource_path,
    record_admin_resource_action,
    secret_values_visible_for_request,
)
from kubernetes_ops.services.admin_resources_list import (
    get_cluster_resource_yaml,
    list_cluster_resources,
)
from kubernetes_ops.services.admin_secret_values import secret_values_payload

__all__ = [
    "AdminResourceError",
    "COMMON_RESOURCES",
    "KubernetesResourceRef",
    "MAX_LIST_ITEMS",
    "READ_VERBS",
    "active_resource_session_for_user",
    "build_resource_ref",
    "cluster_for_value",
    "discover_cluster_resources",
    "get_cluster_resource_yaml",
    "list_cluster_crds",
    "list_cluster_resources",
    "rancher_api_path",
    "rancher_resource_path",
    "record_admin_resource_action",
    "resource_was_redacted",
    "sanitize_kubernetes_resource",
    "secret_values_payload",
    "secret_values_visible_for_request",
]
