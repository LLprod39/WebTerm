from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sAdminAction
from kubernetes_ops.services.admin_manifest_contract import build_resource_manifest_contract
from kubernetes_ops.services.admin_ownership import (
    attach_item_ownership,
    build_admin_resource_ownership,
    summarize_ownership,
)
from kubernetes_ops.services.admin_resource_query import (
    append_query,
    filter_resource_items_for_search,
    list_query_options,
    response_continue_token,
)
from kubernetes_ops.services.admin_resource_sanitizer import resource_was_redacted, sanitize_kubernetes_resource
from kubernetes_ops.services.admin_resource_summary import attach_resource_summaries, build_resource_row_summary
from kubernetes_ops.services.admin_resources_helpers import (
    MAX_LIST_ITEMS,
    AdminResourceError,
    _base_response,
    _provider_get,
    _required_cluster,
    _required_rancher_provider,
    _resource_name,
    active_resource_session_for_user,
    build_resource_ref,
    rancher_resource_path,
    record_admin_resource_action,
    secret_values_visible_for_request,
)
from kubernetes_ops.services.admin_secret_values import bool_value, secret_values_payload
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderTransport


def list_cluster_resources(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    label_selector: str = "",
    field_selector: str = "",
    search: str = "",
    limit: int | str | None = None,
    continue_token: str = "",
    include_managed_fields: bool | str = False,
    include_secret_values: bool | str = False,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    resource_ref = build_resource_ref(
        api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource
    )
    verb = "get" if resource_ref.name else "list"
    session = active_resource_session_for_user(
        user, session_id, cluster, verb=verb, namespace=resource_ref.namespace, kind=resource_ref.kind
    )
    provider = _required_rancher_provider(cluster)
    path = rancher_resource_path(provider, cluster, resource_ref)
    list_options = list_query_options(
        label_selector=label_selector,
        field_selector=field_selector,
        search=search,
        limit=limit,
        continue_token=continue_token,
        include_managed_fields=include_managed_fields,
    )
    if not resource_ref.name:
        path = append_query(path, list_options["provider_params"])
    secret_values_visible = (
        secret_values_visible_for_request(user, resource_ref, include_secret_values) if resource_ref.name else False
    )
    payload = _provider_get(provider, path, transport=transport)
    if resource_ref.name:
        resource = sanitize_kubernetes_resource(payload, allow_secret_values=secret_values_visible)
        ownership = build_admin_resource_ownership(cluster=cluster, ref=resource_ref, resource=resource)
        record_admin_resource_action(
            user=user,
            session=session,
            cluster=cluster,
            ref=resource_ref,
            verb=K8sAdminAction.VERB_GET,
            status=K8sAdminAction.STATUS_COMPLETED,
            response_summary={
                "kind": resource.get("kind"),
                "name": _resource_name(resource),
                "redacted": resource_was_redacted(resource),
                "secret_values_requested": bool_value(include_secret_values),
                "secret_values_visible": secret_values_visible,
            },
        )
        return _base_response(
            "resource_get",
            cluster,
            provider,
            resource_ref,
            path,
            {
                "resource": resource,
                "summary": build_resource_row_summary(resource, ref=resource_ref),
                "redacted": resource_was_redacted(resource),
                "ownership": ownership,
                "secret_values": secret_values_payload(include_secret_values, secret_values_visible),
            },
        )
    raw_payload_items = payload_items(payload)
    item_limit = list_options["limit"]
    raw_items = [
        sanitize_kubernetes_resource(item, include_managed_fields=list_options["include_managed_fields"])
        for item in raw_payload_items[:MAX_LIST_ITEMS]
    ]
    filtered_items = filter_resource_items_for_search(raw_items, list_options["search"])
    visible_items = filtered_items[:item_limit]
    items = attach_resource_summaries(
        attach_item_ownership(cluster=cluster, ref=resource_ref, items=visible_items), ref=resource_ref
    )
    ownership_contexts = [
        item["webterm_ownership"] for item in items if isinstance(item.get("webterm_ownership"), dict)
    ]
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=resource_ref,
        verb=K8sAdminAction.VERB_LIST,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "item_count": len(items),
            "truncated": len(raw_payload_items) > MAX_LIST_ITEMS or len(filtered_items) > item_limit,
            "limit": item_limit,
            "label_selector_present": bool(list_options["provider_params"].get("labelSelector")),
            "field_selector_present": bool(list_options["provider_params"].get("fieldSelector")),
            "search_present": bool(list_options["search"]),
            "continue_present": bool(list_options["provider_params"].get("continue")),
            "include_managed_fields": bool(list_options["include_managed_fields"]),
            "secret_values_requested": bool_value(include_secret_values),
            "secret_values_visible": False,
        },
    )
    secret_values_mode = "list_metadata_only" if resource_ref.kind.lower() == "secret" else "not_applicable"
    return _base_response(
        "resource_list",
        cluster,
        provider,
        resource_ref,
        path,
        {
            "items": items,
            "item_count": len(items),
            "truncated": len(raw_payload_items) > MAX_LIST_ITEMS or len(filtered_items) > item_limit,
            "continue_token": response_continue_token(payload),
            "list_query": list_options["response"],
            "secret_values": secret_values_payload(include_secret_values, False, mode=secret_values_mode),
            "ownership_summary": summarize_ownership(ownership_contexts),
        },
    )


def get_cluster_resource_yaml(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    include_secret_values: bool | str = False,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    if not str(name or "").strip():
        raise AdminResourceError("name is required for YAML view.", code="name_required")
    cluster = _required_cluster(cluster_id)
    resource_ref = build_resource_ref(
        api_version=api_version, kind=kind, namespace=namespace, name=name, resource=resource
    )
    session = active_resource_session_for_user(
        user, session_id, cluster, verb="yaml", namespace=resource_ref.namespace, kind=resource_ref.kind
    )
    provider = _required_rancher_provider(cluster)
    path = rancher_resource_path(provider, cluster, resource_ref)
    secret_values_visible = secret_values_visible_for_request(user, resource_ref, include_secret_values)
    payload = _provider_get(provider, path, transport=transport)
    resource = sanitize_kubernetes_resource(payload, allow_secret_values=secret_values_visible)
    ownership = build_admin_resource_ownership(cluster=cluster, ref=resource_ref, resource=resource)
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=resource_ref,
        verb=K8sAdminAction.VERB_YAML,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "kind": resource.get("kind"),
            "name": _resource_name(resource),
            "redacted": resource_was_redacted(resource),
            "secret_values_requested": bool_value(include_secret_values),
            "secret_values_visible": secret_values_visible,
        },
    )
    return _base_response(
        "resource_yaml",
        cluster,
        provider,
        resource_ref,
        path,
        {
            "resource": resource,
            "redacted": resource_was_redacted(resource),
            "ownership": ownership,
            "manifest": build_resource_manifest_contract(
                resource,
                ref=resource_ref,
                include_secret_values=include_secret_values,
                secret_values_visible=secret_values_visible,
            ),
            "secret_values": secret_values_payload(include_secret_values, secret_values_visible),
        },
    )
