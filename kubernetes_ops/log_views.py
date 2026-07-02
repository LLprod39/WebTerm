from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sPodRef
from kubernetes_ops.services.logs import build_pod_log_snapshot


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops logs API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_pod_logs(request, pod_id: str):
    def handler():
        snapshot = build_pod_log_snapshot(pod_id, tail_lines=request.GET.get("tail"), user=request.user)
        if snapshot is None:
            return JsonResponse({"success": False, "error": "Pod not found"}, status=404)
        _audit_pod_log_snapshot(request, snapshot)
        return JsonResponse(snapshot)

    return _safe_json(handler)


def _audit_pod_log_snapshot(request, snapshot: dict) -> None:
    target = snapshot.get("target") if isinstance(snapshot.get("target"), dict) else {}
    pod = K8sPodRef.objects.select_related("cluster").filter(id=target.get("database_id")).first()
    provider = snapshot.get("provider") if isinstance(snapshot.get("provider"), dict) else {}
    policy = snapshot.get("policy") if isinstance(snapshot.get("policy"), dict) else {}
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action="k8s.pod.logs.snapshot",
        provider=str(provider.get("name") or "")[:50],
        cluster=pod.cluster if pod else None,
        payload={
            "pod_id": target.get("id", ""),
            "pod_name": target.get("name", ""),
            "namespace": target.get("namespace", ""),
            "source": snapshot.get("source", ""),
            "available": bool(snapshot.get("available")),
            "tail_lines": policy.get("requested_tail_lines"),
            "line_count": snapshot.get("line_count", 0),
        },
    )
