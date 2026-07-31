from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_metrics import get_cluster_metrics_snapshot
from kubernetes_ops.services.admin_nodes import list_cluster_nodes
from kubernetes_ops.services.admin_resource_describe import get_cluster_resource_live_describe
from kubernetes_ops.services.admin_resource_detail import get_cluster_resource_detail
from kubernetes_ops.services.admin_resource_events import list_cluster_resource_events
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    discover_cluster_resources,
    get_cluster_resource_yaml,
    list_cluster_crds,
    list_cluster_resources,
)


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes admin resource API failed: %s", exc)
        return internal_error_response(None, exc)


def _error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": str(error),
            "code": error.code,
            "payload": error.payload,
        },
        status=error.status,
    )


def _query(request, name: str, default: str = "") -> str:
    return str(request.GET.get(name) or default).strip()


def _audit(request, action: str, *, payload: dict[str, Any]) -> None:
    session = _session_for_audit(_query(request, "session_id"))
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster if session and session.cluster_id else None,
        payload={
            "session_id": str(session.session_id) if session else _query(request, "session_id")[:80],
            **payload,
        },
    )


def _session_for_audit(session_id: str) -> K8sAdminSession | None:
    if not session_id:
        return None
    try:
        return K8sAdminSession.objects.select_related("cluster").filter(session_id=session_id).first()
    except (TypeError, ValueError, ValidationError):
        return None


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_discovery(request, cluster_id: str):
    def handler():
        try:
            payload = discover_cluster_resources(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
            )
        except AdminResourceError as exc:
            _audit(
                request, "k8s.admin_resource.discovery_rejected", payload={"code": exc.code, "cluster_id": cluster_id}
            )
            return _error_response(exc)
        _audit(request, "k8s.admin_resource.discovery", payload={"cluster_id": cluster_id})
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_list(request, cluster_id: str):
    def handler():
        try:
            payload = list_cluster_resources(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                api_version=_query(request, "api_version", "v1"),
                kind=_query(request, "kind"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                resource=_query(request, "resource"),
                label_selector=_query(request, "label_selector"),
                field_selector=_query(request, "field_selector"),
                search=_query(request, "search"),
                limit=_query(request, "limit"),
                continue_token=_query(request, "continue"),
                include_managed_fields=_query(request, "include_managed_fields"),
                include_secret_values=_query(request, "include_secret_values"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.read_rejected",
                payload={"code": exc.code, "cluster_id": cluster_id, "kind": _query(request, "kind")},
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.read",
            payload={
                "cluster_id": cluster_id,
                "operation": payload["operation"],
                "target": payload["target"],
                "item_count": payload.get("item_count", 1),
                "redacted": bool(payload.get("redacted")),
                "secret_values_requested": bool(payload.get("secret_values", {}).get("requested")),
                "secret_values_visible": bool(payload.get("secret_values", {}).get("visible")),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_yaml(request, cluster_id: str):
    def handler():
        try:
            payload = get_cluster_resource_yaml(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                api_version=_query(request, "api_version", "v1"),
                kind=_query(request, "kind"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                resource=_query(request, "resource"),
                include_secret_values=_query(request, "include_secret_values"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.yaml_rejected",
                payload={
                    "code": exc.code,
                    "cluster_id": cluster_id,
                    "kind": _query(request, "kind"),
                    "name": _query(request, "name"),
                },
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.yaml",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "redacted": bool(payload.get("redacted")),
                "secret_values_requested": bool(payload.get("secret_values", {}).get("requested")),
                "secret_values_visible": bool(payload.get("secret_values", {}).get("visible")),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_detail(request, cluster_id: str):
    def handler():
        try:
            payload = get_cluster_resource_detail(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                api_version=_query(request, "api_version", "v1"),
                kind=_query(request, "kind"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                resource=_query(request, "resource"),
                include_events=_query(request, "include_events", "1"),
                event_limit=_query(request, "event_limit", "50"),
                include_managed_fields=_query(request, "include_managed_fields"),
                include_secret_values=_query(request, "include_secret_values"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.detail_rejected",
                payload={
                    "code": exc.code,
                    "cluster_id": cluster_id,
                    "kind": _query(request, "kind"),
                    "name": _query(request, "name"),
                },
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.detail",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "redacted": bool(payload.get("redacted")),
                "events_available": bool(payload.get("events", {}).get("available")),
                "event_count": int(payload.get("events", {}).get("event_count") or 0),
                "secret_values_requested": bool(payload.get("secret_values", {}).get("requested")),
                "secret_values_visible": bool(payload.get("secret_values", {}).get("visible")),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_describe(request, cluster_id: str):
    def handler():
        try:
            payload = get_cluster_resource_live_describe(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                api_version=_query(request, "api_version", "v1"),
                kind=_query(request, "kind"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                resource=_query(request, "resource"),
                include_events=_query(request, "include_events", "1"),
                include_related=_query(request, "include_related", "1"),
                event_limit=_query(request, "event_limit", "50"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.describe_rejected",
                payload={
                    "code": exc.code,
                    "cluster_id": cluster_id,
                    "kind": _query(request, "kind"),
                    "name": _query(request, "name"),
                },
            )
            return _error_response(exc)
        related = payload.get("related", {})
        _audit(
            request,
            "k8s.admin_resource.describe",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "redacted": bool(payload.get("redacted")),
                "events_available": bool(payload.get("events", {}).get("available")),
                "event_count": int(payload.get("events", {}).get("event_count") or 0),
                "related_pod_count": int(related.get("pods", {}).get("item_count") or 0),
                "related_controller_count": int(related.get("controllers", {}).get("item_count") or 0),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_crds(request, cluster_id: str):
    def handler():
        try:
            payload = list_cluster_crds(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
            )
        except AdminResourceError as exc:
            _audit(request, "k8s.admin_resource.crds_rejected", payload={"code": exc.code, "cluster_id": cluster_id})
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.crds",
            payload={"cluster_id": cluster_id, "item_count": payload.get("item_count", 0), "target": payload["target"]},
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_nodes(request, cluster_id: str):
    def handler():
        try:
            payload = list_cluster_nodes(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                limit=_query(request, "limit"),
            )
        except AdminResourceError as exc:
            _audit(request, "k8s.admin_resource.nodes_rejected", payload={"code": exc.code, "cluster_id": cluster_id})
            return _error_response(exc)
        summary = payload["summary"]
        _audit(
            request,
            "k8s.admin_resource.nodes",
            payload={
                "cluster_id": cluster_id,
                "node_count": summary["node_count"],
                "ready_count": summary["ready_count"],
                "not_ready_count": summary["not_ready_count"],
                "unschedulable_count": summary["unschedulable_count"],
                "tainted_count": summary["tainted_count"],
                "truncated": bool(summary["truncated"]),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_metrics(request, cluster_id: str):
    def handler():
        try:
            payload = get_cluster_metrics_snapshot(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                scope=_query(request, "scope", "nodes"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                limit=_query(request, "limit"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.metrics_rejected",
                payload={"code": exc.code, "cluster_id": cluster_id, "scope": _query(request, "scope", "nodes")},
            )
            return _error_response(exc)
        summary = payload["summary"]
        _audit(
            request,
            "k8s.admin_resource.metrics",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "item_count": summary["item_count"],
                "container_count": summary["container_count"],
                "total_cpu_millicores": summary["total_cpu_millicores"],
                "total_memory_bytes": summary["total_memory_bytes"],
                "truncated": bool(summary["truncated"]),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_admin_resource_events(request, cluster_id: str):
    def handler():
        try:
            payload = list_cluster_resource_events(
                user=request.user,
                session_id=_query(request, "session_id"),
                cluster_id=cluster_id,
                api_version=_query(request, "api_version", "v1"),
                kind=_query(request, "kind"),
                namespace=_query(request, "namespace"),
                name=_query(request, "name"),
                resource=_query(request, "resource"),
                limit=_query(request, "limit", "50"),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.events_rejected",
                payload={
                    "code": exc.code,
                    "cluster_id": cluster_id,
                    "kind": _query(request, "kind"),
                    "namespace": _query(request, "namespace"),
                    "name": _query(request, "name"),
                },
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.events",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "event_count": payload.get("event_count", 0),
                "truncated": bool(payload.get("truncated")),
                "redacted": bool(payload.get("redacted")),
            },
        )
        return JsonResponse(payload)

    return _safe_json(handler)
