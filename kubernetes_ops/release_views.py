from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core_ui.decorators import require_feature
from kubernetes_ops.services.release_readiness_summary import build_kubernetes_release_readiness_summary
from kubernetes_ops.views import _safe_json, _staff_required


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_release_summary(request):
    denied = _staff_required(request)
    if denied:
        return denied
    return _safe_json(lambda: JsonResponse(build_kubernetes_release_readiness_summary(user=request.user)))
