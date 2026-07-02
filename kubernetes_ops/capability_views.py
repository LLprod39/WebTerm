from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core_ui.decorators import require_feature
from kubernetes_ops.services.capabilities import build_kubernetes_capabilities_payload
from kubernetes_ops.views import _safe_json


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_capabilities(request):
    return _safe_json(lambda: JsonResponse(build_kubernetes_capabilities_payload(request.user)))
