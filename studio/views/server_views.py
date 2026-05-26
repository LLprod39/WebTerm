"""
Studio server lookup endpoints used by node configuration dropdowns.
"""

from django.http import JsonResponse

from core_ui.decorators import require_any_feature
from studio.services import list_owned_server_payloads

STUDIO_FEATURE_PIPELINES = "studio_pipelines"
STUDIO_FEATURE_AGENTS = "studio_agents"


@require_any_feature(STUDIO_FEATURE_PIPELINES, STUDIO_FEATURE_AGENTS)
def api_studio_servers(request):
    return JsonResponse(list_owned_server_payloads(request.user), safe=False)
