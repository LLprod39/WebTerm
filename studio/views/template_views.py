"""
Studio pipeline template endpoints.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, PipelineTemplate

STUDIO_FEATURE_PIPELINES = "studio_pipelines"


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _validation_err(errors: list[str], *, prefix: str = "Validation failed") -> JsonResponse:
    message = f"{prefix}: {'; '.join(errors)}"
    return JsonResponse({"error": message, "details": errors}, status=400)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_templates(request):
    templates = PipelineTemplate.objects.all().order_by("category", "name")
    return _ok([template.to_dict() for template in templates])


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_template_use(request, slug: str):
    try:
        template = PipelineTemplate.objects.get(slug=slug)
    except PipelineTemplate.DoesNotExist:
        return _err("Template not found", 404)
    if template.graph_version != CURRENT_PIPELINE_GRAPH_VERSION:
        return _validation_err(
            [
                (
                    f"Template '{template.slug}' uses graph_version={template.graph_version}. "
                    f"Reload built-in templates as V{CURRENT_PIPELINE_GRAPH_VERSION} before using it."
                )
            ],
            prefix="Template is outdated",
        )
    pipeline = template.instantiate_for_user(request.user)
    pipeline.sync_triggers_from_nodes()
    return _ok(pipeline.to_detail_dict(), status=201)
