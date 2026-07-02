from __future__ import annotations

import json
import urllib.parse
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sWorkloadRef
from kubernetes_ops.serializers import serialize_audit_event


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops audit API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _json_body(request) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
    if not isinstance(data, dict):
        return {}, JsonResponse({"success": False, "error": "JSON body must be an object"}, status=400)
    return data, None


def _cluster_or_none(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


def _staff_required(request) -> JsonResponse | None:
    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"success": False, "error": "Admin access is required.", "code": "admin_required"}, status=403)
    return None


def _public_url_for_audit(value: str) -> tuple[str, str, str]:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL.")
    public_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return public_url[:500], parsed.netloc[:180], parsed.scheme


def _cluster_for_deeplink(data: dict[str, Any]) -> K8sCluster | None:
    cluster_id = str(data.get("cluster_id") or "").strip()
    if cluster_id:
        cluster = _cluster_or_none(cluster_id)
        if cluster is not None:
            return cluster
    target_id = str(data.get("target_id") or "").strip()
    numeric = target_id.split("_", 1)[-1] if "_" in target_id else target_id
    if numeric.isdigit():
        if str(data.get("target_type") or "").strip() == "app":
            app = K8sAppRef.objects.filter(id=int(numeric)).select_related("cluster").first()
            return app.cluster if app else None
        if str(data.get("target_type") or "").strip() == "workload":
            workload = K8sWorkloadRef.objects.filter(id=int(numeric)).select_related("cluster").first()
            return workload.cluster if workload else None
    return None


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_audit(request):
    events = K8sAuditEvent.objects.select_related("cluster", "user").all()[:100]
    return _safe_json(lambda: JsonResponse({"success": True, "events": [serialize_audit_event(event) for event in events]}))


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_deeplink_audit(request):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        target_type = str(data.get("target_type") or "").strip()[:60]
        target_id = str(data.get("target_id") or "").strip()[:120]
        target_name = str(data.get("target_name") or "").strip()[:180]
        link_key = str(data.get("link_key") or "").strip()[:80]
        if not target_type or not link_key:
            return JsonResponse({"success": False, "error": "target_type and link_key are required."}, status=400)
        try:
            public_url, host, scheme = _public_url_for_audit(str(data.get("url") or ""))
        except ValueError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        event = K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.deeplink.open",
            provider=str(data.get("provider") or "").strip()[:50],
            cluster=_cluster_for_deeplink(data),
            payload={
                "target_type": target_type,
                "target_id": target_id,
                "target_name": target_name,
                "link_key": link_key,
                "url": public_url,
                "host": host,
                "scheme": scheme,
            },
        )
        return JsonResponse({"success": True, "event": serialize_audit_event(event)})

    return _safe_json(handler)
