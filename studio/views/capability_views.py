"""
Studio capability registry endpoint.
"""

from django.views.decorators.http import require_GET

from core_ui.decorators import require_feature
from studio.capability_registry import build_studio_capability_registry
from studio.node_manifest import node_manifest_payload
from studio.readiness import build_studio_readiness_report
from studio.services import list_owned_server_payloads
from studio.views.common import STUDIO_FEATURE_PIPELINES, _ok


def _truthy_query(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _pipeline_ids_from_query(request) -> list[int]:
    ids: list[int] = []
    for raw in request.GET.getlist("pipeline_id"):
        for item in str(raw or "").split(","):
            value = item.strip()
            if value:
                ids.append(int(value))
    return ids


@require_GET
@require_feature(STUDIO_FEATURE_PIPELINES)
def api_capabilities(request):
    servers = list_owned_server_payloads(request.user)
    return _ok(build_studio_capability_registry(request.user, server_count=len(servers)))


@require_GET
@require_feature(STUDIO_FEATURE_PIPELINES)
def api_node_manifests(request):
    nodes = node_manifest_payload()
    return _ok({"version": 1, "count": len(nodes), "nodes": nodes})


@require_GET
@require_feature(STUDIO_FEATURE_PIPELINES)
def api_readiness(request):
    try:
        pipeline_ids = _pipeline_ids_from_query(request)
    except ValueError:
        return _ok({"error": "pipeline_id must be an integer"}, status=400)
    return _ok(
        build_studio_readiness_report(
            request.user,
            pipeline_ids=pipeline_ids or None,
            active_only=_truthy_query(request.GET.get("active_only")),
            entry_node_id=request.GET.get("entry_node_id", ""),
        )
    )
