"""
Studio capability registry endpoint.
"""

from django.views.decorators.http import require_GET

from core_ui.decorators import require_feature
from studio.capability_registry import build_studio_capability_registry
from studio.node_manifest import node_manifest_payload
from studio.services import list_owned_server_payloads
from studio.views.common import STUDIO_FEATURE_PIPELINES, _ok


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
