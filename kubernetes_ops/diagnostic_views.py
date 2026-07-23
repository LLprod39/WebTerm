from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent
from kubernetes_ops.services.diagnostics_summary import build_diagnostics_summary, diagnostics_summary_audit_payload


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes diagnostics API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_diagnostics_summary(request):
    def handler():
        payload, error = build_diagnostics_summary(
            scope=request.GET.get("scope", ""),
            user=request.user,
            cluster_id=request.GET.get("cluster_id", ""),
            namespace=request.GET.get("namespace", ""),
            namespace_id=request.GET.get("namespace_id", ""),
            workload_id=request.GET.get("workload_id", ""),
            pod_id=request.GET.get("pod_id", ""),
            network_id=request.GET.get("network_id", ""),
        )
        if payload is None:
            return JsonResponse(
                {"success": False, "error": _error_message(error), "code": error}, status=_status_for_error(error)
            )
        audit_payload = diagnostics_summary_audit_payload(payload)
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.diagnostics.summary",
            provider="webterm",
            cluster_id=_numeric_cluster_id(audit_payload.get("cluster_id")),
            payload=audit_payload,
        )
        return JsonResponse(payload)

    return _safe_json(handler)


def _status_for_error(error: str) -> int:
    if error == "invalid_scope":
        return 400
    return 404


def _error_message(error: str) -> str:
    return {
        "invalid_scope": "scope must be cluster, namespace, workload, pod, or network.",
        "cluster_not_found": "Cluster not found.",
        "namespace_not_found": "Namespace not found.",
        "workload_not_found": "Workload not found.",
        "pod_not_found": "Pod not found.",
        "network_not_found": "Network object not found.",
    }.get(error, "Diagnostics target not found.")


def _numeric_cluster_id(value: object) -> int | None:
    text = str(value or "").strip().removeprefix("cluster_")
    return int(text) if text.isdigit() else None
